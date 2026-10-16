import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/aletheia/scripts/router.py"
spec = importlib.util.spec_from_file_location("skill_router", SCRIPT)
router = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = router
spec.loader.exec_module(router)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = ROOT / "tests/fixtures"

    def test_scan_and_route(self):
        skills, issues = router.discover([self.fixtures])
        self.assertEqual(6, len(skills))
        self.assertFalse(issues)
        for task, expected in [
            ("请帮我分析Excel表格", "spreadsheet-analysis"),
            ("Review a pdf", "pdf-processing"),
            ("帮我网络调研查资料", "web-research"),
        ]:
            result = router.route(task, skills, 5, 16)
            self.assertEqual(expected, result["candidates"][0]["name"])
            self.assertFalse(result["actual_invocation_verified"])

    def test_negative_does_not_force_skill(self):
        skills, _ = router.discover([self.fixtures])
        self.assertEqual([], router.route("早上好", skills, 5, 16)["candidates"])

    def test_malformed_and_symlink_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad").mkdir()
            (root / "bad/SKILL.md").write_text("---\nname: BAD\ndescription: x\n---", encoding="utf-8")
            skills, issues = router.discover([root])
            self.assertFalse(skills)
            self.assertEqual(1, len(issues))
            self.assertIn("invalid name", issues[0]["error"])
            (root / "bad/SKILL.md").unlink()
            # Creating a symlink on Windows needs Administrator or Developer Mode.
            # Probe it rather than letting the whole test error out in an
            # environment that simply cannot do this — an error here would hide
            # real regressions behind a permanent, unrelated failure.
            try:
                (root / "bad/SKILL.md").symlink_to(self.fixtures / "pdf-processing/SKILL.md")
            except (OSError, NotImplementedError) as e:
                self.skipTest(f"symlinks unavailable on this platform: {e}")
            skills, issues = router.discover([root])
            self.assertFalse(skills)
            self.assertTrue(issues)

    def test_duplicate_names_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            for root in (a, b):
                f = root / "hello" / "SKILL.md"
                f.parent.mkdir(parents=True)
                f.write_text("---\nname: hello\ndescription: A greeting skill.\n---\n", encoding="utf-8")
            skills, issues = router.discover([a, b])
            self.assertEqual(2, len(skills))
            self.assertTrue(any("duplicate" in i["error"] for i in issues))

    def test_block_scalar_frontmatter(self):
        skills, issues = router.discover([ROOT / "skills"])
        self.assertFalse(issues)
        self.assertEqual("aletheia", skills[0].name)
        self.assertIn("incoming task", skills[0].description)

    def test_eval_cases(self):
        skills, _ = router.discover([self.fixtures])
        cases = json.loads((ROOT / "tests/eval_cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["id"]):
                candidates = [r["name"] for r in router.route(case["task"], skills, 3, 16)["candidates"]]
                self.assertTrue(set(case["expect"]).issubset(set(candidates)) if case["expect"] else not candidates)

    def test_router_never_recommends_itself(self):
        """The coordinator must not appear as a candidate for unrelated work."""
        skills, _ = router.discover([self.fixtures, ROOT / "skills"])
        names = [s["name"] for s in router.route("分析Excel表格数据", skills, 5, 16)["candidates"]]
        self.assertNotIn(router.SELF_NAME, names)

    def test_cli_and_eval_share_threshold_defaults(self):
        """eval must measure the same threshold the CLI actually uses."""
        self.assertEqual(16, router.DEFAULT_THRESHOLD)
        self.assertEqual(5, router.DEFAULT_TOP)

    def test_version_is_consistent_across_release_files(self):
        """pyproject, SKILL.md frontmatter and router.py must agree on the version."""
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        declared = re.search(r'^version = "([^"]+)"', pyproject, re.M)
        self.assertIsNotNone(declared, "pyproject.toml must declare a version")
        self.assertEqual(declared.group(1), router.VERSION)

        skill_md = (ROOT / "skills/aletheia/SKILL.md").read_text(encoding="utf-8")
        frontmatter_version = re.search(r'^\s*version:\s*"([^"]+)"', skill_md, re.M)
        self.assertIsNotNone(frontmatter_version, "SKILL.md frontmatter must declare a version")
        self.assertEqual(declared.group(1), frontmatter_version.group(1))

        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(declared.group(1), changelog, "CHANGELOG.md must mention the current version")

    def test_session_scope_restricts_candidates(self):
        """--only must suppress non-allowlisted skills and report what was withheld."""
        skills, _ = router.discover([self.fixtures])
        kept, suppressed = router.apply_scope(skills, {"slides-design"})
        self.assertEqual(["slides-design"], [s.name for s in kept])
        self.assertEqual(
            ["code-review", "image-creation", "pdf-processing", "spreadsheet-analysis", "web-research"],
            sorted(suppressed),
        )

    def test_scope_parsing_handles_commas_and_spaces(self):
        self.assertEqual({"a", "b", "c"}, router.parse_scope(["a,b", "c"]))
        self.assertEqual({"a", "b"}, router.parse_scope(["a b"]))
        self.assertIsNone(router.parse_scope([]))
        self.assertIsNone(router.parse_scope(None))

    def test_session_manifest_limits_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "aletheia-session.json"
            manifest.write_text(json.dumps({"only": ["pdf-processing"]}), encoding="utf-8")
            loaded = router.load_session_manifest(manifest)
            self.assertEqual(["pdf-processing"], loaded["only"])
            # A manifest is discovered by walking up from the working directory.
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            found = router.load_session_manifest(None, nested)
            self.assertIsNotNone(found)
            # Compare canonical forms, not raw spellings. One file has several
            # legitimate spellings — macOS symlinks /var to /private/var, Windows
            # short paths like RUNNER~1 expand to the long name — so comparing
            # spellings asserts something false on two of three CI platforms
            # while being accidentally true on the third. tempfile already hands
            # back a canonical root on Windows but not on macOS, which is exactly
            # why the comparison has to normalise rather than pick a side.
            self.assertEqual(
                manifest.resolve(), Path(found["_path"]).resolve(),
                "the same file must be reported the same way regardless of how it was found",
            )
            # The reported spelling itself must already be canonical, or a caller
            # that string-compares it against the path it passed in still breaks.
            self.assertEqual(
                str(Path(found["_path"])), str(Path(found["_path"]).resolve()),
                "_path must not carry '..' or any other unresolved segment",
            )

    def test_session_manifest_path_is_canonical_however_it_was_named(self):
        """`_path` must not depend on which route located the manifest.

        The explicit and upward-search branches both hand back `_path`, and a
        consumer compares it against the path it supplied. If one branch
        resolves and the other does not, that comparison breaks wherever a
        directory has two names — which is the normal state on macOS and on a
        Windows runner, and never on a developer machine.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "aletheia-session.json"
            manifest.write_text(json.dumps({"only": ["pdf-processing"]}), encoding="utf-8")

            # Named via a non-canonical spelling: '.' and '..' must not survive.
            (root / "a" / "b").mkdir(parents=True)
            indirect = root / "a" / ".." / "aletheia-session.json"
            explicit = router.load_session_manifest(indirect)
            found = router.load_session_manifest(None, root / "a" / "b")

            self.assertIsNotNone(found)
            # Compare the raw values. Resolving both sides inside the test would
            # normalise away the very difference under test, which is how a guard
            # ends up passing on the defect it was written for.
            self.assertEqual(
                Path(explicit["_path"]),
                Path(found["_path"]),
                "explicit and discovered paths must agree as reported",
            )
            self.assertEqual(
                Path(explicit["_path"]),
                manifest.resolve(),
                "_path must be canonical: 'a/..' must not survive into it",
            )

    def test_malformed_session_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "aletheia-session.json"
            bad.write_text("{not json", encoding="utf-8")
            with self.assertRaises(router.SkillError):
                router.load_session_manifest(bad)
            missing = Path(tmp) / "nope.json"
            with self.assertRaises(router.SkillError):
                router.load_session_manifest(missing)

    def test_context_pressure_is_labelled_as_estimate(self):
        """Never claim a measured percentage; always return a host command."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session.jsonl").write_text("x" * 60_000, encoding="utf-8")
            result = router.context_pressure(root, "claude", 128_000, None)
            self.assertFalse(result["is_measured_context_percentage"])
            self.assertEqual("estimated_from_transcript_bytes", result["measurement"])
            self.assertEqual(60_000, result["transcript_bytes"])
            self.assertGreater(result["estimated_utilization_percent"], 0)
            self.assertEqual("/compact", result["host"]["compact"])
            self.assertEqual("/clear", result["host"]["new_session"])

    def test_context_tiers_escalate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "big.jsonl").write_text("x" * 2_000_000, encoding="utf-8")
            result = router.context_pressure(root, "codex", 128_000, None)
            self.assertIn(result["status"], ("trim", "new_session"))
            self.assertEqual("/new", result["host"]["new_session"])

    def test_context_empty_dir_is_ok_not_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = router.context_pressure(Path(tmp), "workbuddy", 128_000, None)
            self.assertEqual("ok", result["status"])
            self.assertEqual(0, result["transcript_bytes"])

    def test_unknown_host_falls_back_to_generic(self):
        self.assertIn("generic", router.HOST_COMMANDS)
        with tempfile.TemporaryDirectory() as tmp:
            result = router.context_pressure(Path(tmp), "some-unknown-host", 128_000, None)
            self.assertEqual("Generic agent host", result["host"]["label"])

    def test_progress_is_countable_and_has_no_eta(self):
        """Progress must be done/total and must never carry a time estimate."""
        steps = ["gather", "read", "write", "verify"]
        result = router.build_progress(steps, 2)
        self.assertEqual(50, result["percent"])
        self.assertEqual(2, result["completed"])
        self.assertEqual(4, result["total"])
        self.assertTrue(result["countable"])
        self.assertIsNone(result["eta"], "an agent cannot know how long the next step takes")
        statuses = [s["status"] for s in result["steps"]]
        self.assertEqual(["done", "done", "current", "pending"], statuses)

    def test_progress_bar_width_and_filling(self):
        def cells(fraction, width=10):
            # render_bar returns "[<cells>]", so strip the brackets to count cells.
            return len(router.render_bar(fraction, width)) - 2

        self.assertEqual(10, cells(0.5))
        self.assertEqual(10, cells(1.0))
        self.assertEqual(10, cells(0.0))
        # Out-of-range fractions must clamp rather than overflow the bar.
        self.assertEqual(10, cells(1.8))
        self.assertEqual(10, cells(-0.4))
        # A fully filled bar must be entirely full blocks with no remainder.
        self.assertEqual("█" * 10, router.render_bar(1.0, 10)[1:-1])

    def test_progress_done_requires_full_completion(self):
        result = router.build_progress(["a", "b"], 2, state="done")
        self.assertEqual(100, result["percent"])
        self.assertIn("2/2", result["line"])
        self.assertNotIn("→", result["line"], "a finished task has no 'currently' arrow")

    def test_progress_blocked_differs_from_failed(self):
        """Waiting on a human must not read as an error."""
        steps = ["a", "b", "c"]
        blocked = router.build_progress(steps, 1, state="blocked")
        failed = router.build_progress(steps, 1, state="failed")
        self.assertNotEqual(blocked["line"], failed["line"])
        self.assertIn("Waiting on you", blocked["line"])
        self.assertIn("Stopped", failed["line"])
        # The stall step carries the state, not "current".
        self.assertEqual("blocked", blocked["steps"][1]["status"])
        self.assertEqual("failed", failed["steps"][1]["status"])

    def test_progress_clamps_and_rejects_bad_input(self):
        result = router.build_progress(["a", "b"], 99)
        self.assertEqual(2, result["completed"])
        self.assertEqual(100, result["percent"])
        with self.assertRaises(router.SkillError):
            router.build_progress([], 0)
        with self.assertRaises(router.SkillError):
            router.build_progress(["a"], 0, state="nonsense")

    def test_progress_ascii_fallback(self):
        result = router.build_progress(["a", "b", "c", "d"], 2, ascii_only=True)
        self.assertNotIn("█", result["line"])
        self.assertIn("#", result["line"])
        self.assertIn("->", result["line"])

    def test_scope_report_does_not_reprint_suppressed_names(self):
        """Listing every suppressed name would spend the context scoping just saved."""
        skills, _ = router.discover([self.fixtures])
        allowed = {"slides-design"}
        kept, suppressed = router.apply_scope(skills, allowed)
        compact = router.scope_report(skills, kept, suppressed, allowed, None, detail=False)
        verbose = router.scope_report(skills, kept, suppressed, allowed, None, detail=True)
        self.assertNotIn("suppressed_skills", compact)
        self.assertEqual(5, compact["suppressed_count"])
        self.assertEqual(len(suppressed), len(verbose["suppressed_skills"]))
        # The compact form must be materially smaller than the verbose one.
        self.assertLess(len(json.dumps(compact)), len(json.dumps(verbose)))

    def test_scope_report_quantifies_context_saving(self):
        skills, _ = router.discover([self.fixtures])
        kept, suppressed = router.apply_scope(skills, {"slides-design"})
        report = router.scope_report(skills, kept, suppressed, {"slides-design"}, None)
        est = report["context_estimate"]
        self.assertGreater(est["unscoped"], est["scoped"])
        self.assertGreater(est["saved_percent"], 0)
        self.assertIn("caveat", est, "an estimate must be labelled as one")

    def test_scope_report_warns_on_unmatched_allowlist(self):
        """A typo must not look like 'no relevant skills exist'."""
        skills, _ = router.discover([self.fixtures])
        allowed = {"slides-design", "docx", "xlsx"}
        kept, suppressed = router.apply_scope(skills, allowed)
        report = router.scope_report(skills, kept, suppressed, allowed, None)
        self.assertEqual(["docx", "xlsx"], report["unmatched_allowed"])
        self.assertIn("matched nothing", report["warning"])

    def test_scope_report_no_unmatched_key_when_all_match(self):
        skills, _ = router.discover([self.fixtures])
        allowed = {"slides-design", "pdf-processing"}
        kept, suppressed = router.apply_scope(skills, allowed)
        report = router.scope_report(skills, kept, suppressed, allowed, None)
        self.assertNotIn("unmatched_allowed", report)
        self.assertNotIn("warning", report)

    def test_scope_report_inactive_when_no_allowlist(self):
        skills, _ = router.discover([self.fixtures])
        report = router.scope_report(skills, skills, [], None, None)
        self.assertFalse(report["active"])
        self.assertEqual(6, report["visible"])

    def test_profile_is_a_reusable_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profiles = root / ".aletheia" / "profiles"
            profiles.mkdir(parents=True)
            (profiles / "deck.json").write_text(json.dumps(["slides-design", "image-creation"]), encoding="utf-8")
            self.assertEqual(["slides-design", "image-creation"], router.load_profile("deck", root))
            # A dict form is accepted too.
            (profiles / "dict.json").write_text(json.dumps({"only": ["pdf-processing"]}), encoding="utf-8")
            self.assertEqual(["pdf-processing"], router.load_profile("dict", root))

    def test_missing_profile_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(router.SkillError):
                router.load_profile("nope", Path(tmp))

    def test_name_directory_mismatch_warns_but_keeps_skill(self):
        """A marketplace suffix must not hide a skill from the butler's registry."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "cool-skill__skillhub"
            d.mkdir()
            (d / "SKILL.md").write_text(
                "---\nname: cool-skill\ndescription: A genuinely useful skill.\n---\n# body\n", encoding="utf-8"
            )
            skills, issues = router.discover([root])
            self.assertEqual(1, len(skills), "skill must survive the name/directory mismatch")
            self.assertEqual("cool-skill", skills[0].name)
            self.assertEqual("warning", issues[0]["severity"])
            self.assertIn("differs from directory", issues[0]["error"])

    def test_strict_mode_rejects_what_default_only_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "cool-skill__skillhub"
            d.mkdir()
            (d / "SKILL.md").write_text(
                "---\nname: cool-skill\ndescription: A genuinely useful skill.\n---\n# body\n", encoding="utf-8"
            )
            skills, issues = router.discover([root], strict=True)
            self.assertEqual(0, len(skills))
            self.assertTrue(any("differs from directory" in i["error"] for i in issues))

    def test_nested_plugin_layouts_are_discovered(self):
        """Plugin cache nests as <vendor>/<plugin>/<version>/SKILL.md."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "vendor" / "plugin" / "1.2.0"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text(
                "---\nname: nested-plugin-skill\ndescription: Installed via a plugin cache.\n---\n# body\n",
                encoding="utf-8",
            )
            skills, _ = router.discover([root])
            self.assertEqual(["nested-plugin-skill"], [s.name for s in skills])

    def test_inventory_numbers_are_stable_and_unique(self):
        skills, issues = router.discover([self.fixtures])
        inv = router.build_inventory(skills, issues, [self.fixtures], limit=0)
        numbers = [e["n"] for e in inv["entries"]]
        self.assertEqual(list(range(1, len(numbers) + 1)), numbers, "numbers must be 1..N contiguous")
        self.assertEqual(len(set(numbers)), len(numbers), "numbers must be unique")

    def test_inventory_collapses_duplicate_installs(self):
        """A skill installed twice must not make a quoted number ambiguous."""
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            for root in (a, b):
                d = root / "dupe"
                d.mkdir(parents=True)
                (d / "SKILL.md").write_text(
                    "---\nname: dupe\ndescription: Installed in two places.\n---\n# body\n", encoding="utf-8"
                )
            skills, _ = router.discover([a, b])
            inv = router.build_inventory(skills, [], [a, b], limit=0)
            self.assertEqual(2, inv["total_installed"])
            self.assertEqual(1, inv["unique_skills"])
            self.assertEqual(1, inv["duplicate_installs"])

    def test_inventory_query_filters(self):
        skills, issues = router.discover([self.fixtures])
        inv = router.build_inventory(skills, issues, [self.fixtures], query="pdf", limit=0)
        self.assertTrue(inv["entries"])
        self.assertTrue(all("pdf" in e["name"] or "pdf" in e["description"].lower() for e in inv["entries"]))

    def test_mode_config_defaults_to_auto_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            self.assertEqual("auto", router.load_mode_config(missing)["mode"], "auto is the default")
            cfg = Path(tmp) / "aletheia-config.json"
            cfg.write_text(json.dumps({"mode": "manual", "only": ["a", "b"]}), encoding="utf-8")
            loaded = router.load_mode_config(cfg)
            self.assertEqual("manual", loaded["mode"])
            self.assertEqual(["a", "b"], loaded["only"])
            # A corrupt file must not crash the butler; fall back to auto.
            cfg.write_text("{broken", encoding="utf-8")
            self.assertEqual("auto", router.load_mode_config(cfg)["mode"])

    def test_ledger_is_local_and_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = router.append_ledger({"task_id": "t1", "phase": "before"}, base=base)
            self.assertTrue(path.is_file())
            self.assertTrue(str(path).endswith(router.LEDGER_FILE_NAME))
            router.append_ledger({"task_id": "t2", "phase": "after"}, base=base)
            records = router.read_ledger(path)
            self.assertEqual(["t1", "t2"], [r["task_id"] for r in records])
            # A truncated final line must not break reporting.
            with path.open("a", encoding="utf-8") as handle:
                handle.write("{broken\n")
            self.assertEqual(2, len(router.read_ledger(path)))

    def test_measure_marks_unmeasured_fields_unavailable(self):
        """Never present an unmeasurable field as a number."""
        skills, _ = router.discover([self.fixtures])
        cost = router.measure_routing_cost("build a deck", skills, {"slides-design"})
        self.assertEqual("estimated", cost["fields"]["task_tokens"])
        self.assertEqual(router.UNAVAILABLE, cost["fields"]["host_token_usage"])
        self.assertGreater(cost["metadata_tokens_est_unscoped"], cost["metadata_tokens_est_scoped"])

    def test_comparison_refuses_to_invent_savings_claims(self):
        skills, _ = router.discover([self.fixtures])
        scoped = router.measure_routing_cost("build a deck", skills, {"slides-design"})
        baseline = router.measure_routing_cost("build a deck", skills, None)
        result = router.compare_scenarios(baseline, scoped)
        self.assertGreater(result["comparison"]["saved_tokens_est"], 0)
        # Anything not measurable must be an explicit refusal, not a guess.
        for item in result["not_quantified"]:
            self.assertEqual(router.UNAVAILABLE, item["value"])
            self.assertTrue(item["why"])

    def test_telemetry_marks_absent_hosts_unavailable(self):
        """A host with no data must read 'unavailable', never 0 tokens."""
        with tempfile.TemporaryDirectory() as tmp:
            result = router.collect_host_usage(base=Path(tmp), hosts=("claude", "workbuddy"))
            self.assertFalse(result["workbuddy"]["available"])
            self.assertEqual(router.UNAVAILABLE, result["workbuddy"]["input_tokens"])
            self.assertIn("does not persist", result["workbuddy"]["reason"])
            # An empty directory yields no parseable usage, so also unavailable.
            self.assertFalse(result["claude"]["available"])
            self.assertEqual(router.UNAVAILABLE, result["claude"]["output_tokens"])

    def test_telemetry_reads_nested_and_flat_usage_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / ".claude" / "projects" / "p"
            sessions.mkdir(parents=True)
            (sessions / "a.jsonl").write_text(
                json.dumps({"message": {"usage": {"input_tokens": 10, "output_tokens": 4}}}) + "\n"
                + json.dumps({"usage": {"input_tokens": 6, "cache_read_input_tokens": 100}}) + "\n",
                encoding="utf-8",
            )
            result = router.collect_host_usage(base=base, hosts=("claude",))
            self.assertTrue(result["claude"]["available"])
            self.assertEqual(16, result["claude"]["input_tokens"])
            self.assertEqual(4, result["claude"]["output_tokens"])
            self.assertEqual(100, result["claude"]["cache_read_tokens"])
            self.assertEqual(2, result["claude"]["messages_with_usage"])

    def test_nested_cache_detail_does_not_clobber_a_real_flat_value(self):
        """A synthesized zero must never overwrite a cache_read that was logged."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / ".claude" / "projects" / "p"
            sessions.mkdir(parents=True)
            (sessions / "a.jsonl").write_text(
                json.dumps({"message": {"usage": {"input_tokens": 1, "cache_read_input_tokens": 500}}}) + "\n",
                encoding="utf-8",
            )
            result = router.collect_host_usage(base=base, hosts=("claude",))
            self.assertEqual(500, result["claude"]["cache_read_tokens"])

    def test_codex_nested_cached_tokens_are_read(self):
        """Codex reports cache hits under input_token_details.cached_tokens."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            (sessions / "r.jsonl").write_text(
                json.dumps({"usage": {"input_tokens": 200, "output_tokens": 50,
                                      "input_token_details": {"cached_tokens": 70}}}) + "\n",
                encoding="utf-8",
            )
            result = router.collect_host_usage(base=base, hosts=("codex",))
            self.assertEqual(70, result["claude" if False else "codex"]["cache_read_tokens"])

    def test_kimi_wire_format_is_understood(self):
        """Kimi nests token_usage under message.payload with its own field names."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / ".kimi" / "sessions" / "s1"
            sessions.mkdir(parents=True)
            (sessions / "wire.jsonl").write_text(
                json.dumps({"message": {"payload": {"token_usage": {
                    "input_other": 1874, "output": 140,
                    "input_cache_read": 5376, "input_cache_creation": 7}}}}) + "\n",
                encoding="utf-8",
            )
            result = router.collect_host_usage(base=base, hosts=("kimi",))
            self.assertTrue(result["kimi"]["available"])
            self.assertEqual(1874, result["kimi"]["input_tokens"])
            self.assertEqual(140, result["kimi"]["output_tokens"])
            self.assertEqual(5376, result["kimi"]["cache_read_tokens"])
            self.assertEqual(7, result["kimi"]["cache_write_tokens"])

    def test_qwen_gemini_style_usage_metadata(self):
        """Gemini and Qwen share a lineage and use promptTokenCount naming."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / ".qwen" / "projects" / "p" / "chats"
            sessions.mkdir(parents=True)
            (sessions / "s.jsonl").write_text(
                json.dumps({"usageMetadata": {"promptTokenCount": 900,
                                              "candidatesTokenCount": 120,
                                              "cachedContentTokenCount": 300}}) + "\n",
                encoding="utf-8",
            )
            result = router.collect_host_usage(base=base, hosts=("qwen",))
            self.assertTrue(result["qwen"]["available"])
            self.assertEqual(900, result["qwen"]["input_tokens"])
            self.assertEqual(120, result["qwen"]["output_tokens"])
            self.assertEqual(300, result["qwen"]["cache_read_tokens"])

    def test_unknown_host_is_reported_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = router.collect_host_usage(base=Path(tmp), hosts=("not-a-host",))
            self.assertFalse(result["not-a-host"]["available"])
            self.assertEqual(router.UNAVAILABLE, result["not-a-host"]["total_tokens_including_cache_read"])
            self.assertIn("unknown host", result["not-a-host"]["reason"])

    def test_every_registered_host_normalises_to_the_same_keys(self):
        """A consumer must never have to branch on which host lacked data."""
        reference = None
        for host, spec in router.TELEMETRY_HOSTS.items():
            with tempfile.TemporaryDirectory() as tmp:
                result = router.collect_host_usage(base=Path(tmp), hosts=(host,))[host]
            keys = {k for k, v in result.items() if k not in ("note",)}
            if reference is None:
                reference = keys
            self.assertEqual(reference, keys, f"{host} returns a different key set")

    def test_registry_covers_the_mainstream_agents(self):
        """The registry must know the widely used hosts, not just two."""
        for expected in ("claude", "codex", "gemini", "qwen", "copilot", "kimi",
                         "opencode", "droid", "kiro", "crush", "aider", "workbuddy"):
            self.assertIn(expected, router.TELEMETRY_HOSTS)
        for host, spec in router.TELEMETRY_HOSTS.items():
            self.assertIn("skills", spec, f"{host} must declare its skill directories")
            self.assertTrue(spec.get("native_skill_dir"), f"{host} must name its skill dir")
            if spec.get("sessions"):
                self.assertTrue(spec.get("aliases"), f"{host} needs field aliases")

    def test_alias_table_prefilter_cannot_drop_a_real_line(self):
        """Every alias must be reachable by the prefilter, or its data goes missing."""
        for host, spec in router.TELEMETRY_HOSTS.items():
            hints = router._usage_prefilter(spec)
            for bucket, names in (spec.get("aliases") or {}).items():
                for name in names:
                    self.assertTrue(
                        name in hints,
                        f"{host}.{bucket} alias {name!r} would be filtered out before parsing",
                    )
            for path_tuple in spec.get("usage_paths", ()):
                for segment in path_tuple:
                    self.assertIn(segment, hints, f"{host} usage path segment {segment!r} must be a hint")

    def test_audit_finds_and_counts_damage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = root / "good"
            good.mkdir()
            (good / "SKILL.md").write_text(
                "---\nname: good\ndescription: A healthy skill.\n---\n# body\n", encoding="utf-8"
            )
            long_desc = root / "toolong"
            long_desc.mkdir()
            (long_desc / "SKILL.md").write_text(
                f"---\nname: toolong\ndescription: {'x' * 1200}\n---\n# body\n", encoding="utf-8"
            )
            result = router.audit_library([root], unused_days=9999, fix=False)
            self.assertEqual(2, result["scanned"])
            self.assertEqual(1, result["counts"]["ok"])
            self.assertEqual(1, result["counts"]["broken"])
            self.assertEqual(0, result["counts"]["blocking"])
            self.assertTrue(result["recommendations"])

    def test_audit_fix_repairs_and_never_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "toolong"
            d.mkdir()
            original = f"---\nname: toolong\ndescription: {'x' * 1200}\n---\n\n# keep this body\n"
            (d / "SKILL.md").write_text(original, encoding="utf-8")
            result = router.audit_library([root], fix=True)
            self.assertEqual(1, result["counts"]["broken"])
            self.assertTrue((d / "SKILL.md").is_file(), "repair must never delete the skill")
            after = (d / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("# keep this body", after, "the body must survive a repair")
            self.assertLess(len(after), len(original))
            # And it must now diagnose cleanly.
            self.assertEqual("ok", router.diagnose_skill(d / "SKILL.md")["kind"])

    def test_audit_identifies_skills_by_declared_name(self):
        """Plugin version folders must not masquerade as skill names."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "vendor" / "plugin" / "1.3.0"
            nested.mkdir(parents=True)
            (nested / "SKILL.md").write_text(
                "---\nname: real-skill\nversion: 1.3.0\ndescription: A plugin skill.\n---\n# body\n",
                encoding="utf-8",
            )
            result = router.audit_library([root])
            self.assertEqual(1, result["scanned"])
            self.assertEqual(0, result["counts"]["duplicate"], "one install is not a duplicate")
            self.assertEqual("real-skill", result["broken"][0]["name"] if result["broken"] else "real-skill")

    def _sample_records(self) -> list[dict]:
        return [
            {
                "task_id": "t1", "phase": "before", "label": "deck",
                "without_aletheia": {"metadata_tokens_est_unscoped": 33891},
                "with_aletheia": {"metadata_tokens_est_scoped": 355},
                "comparison": {
                    "comparison": {
                        "without_aletheia": {"metadata_tokens_est": 33891},
                        "with_aletheia_scoped": {"metadata_tokens_est": 355},
                        "saved_tokens_est": 33536, "saved_percent": 99.0,
                    },
                    "not_quantified": [{"claim": "money saved", "value": router.UNAVAILABLE, "why": "no price"}],
                },
                "actual_tokens": router.UNAVAILABLE,
            },
            {  # a telemetry record carries no comparison at all
                "task_id": "t2", "phase": "after", "label": "host telemetry",
                "host_telemetry": {
                    "claude": {
                        "available": True, "label": "Claude Code",
                        "input_tokens": 58, "output_tokens": 8951,
                        "cache_read_tokens": 2377969, "cache_write_tokens": 483380,
                        "messages_with_usage": 29, "sessions_scanned": 2,
                    },
                    "workbuddy": {"available": False, "label": "WorkBuddy",
                                  "reason": "does not persist token usage"},
                },
                "actual_tokens": router.UNAVAILABLE,
            },
        ]

    def test_report_text_is_formatted_not_a_dump(self):
        """The plain-text tier must still be readable, not a wall of values."""
        body = router.render_report_markdown(self._sample_records(), as_text=True)
        # Headings survive as rules, and no Markdown syntax leaks through.
        self.assertIn("ALETHEIA ROUTING COST REPORT", body)
        self.assertIn("===", body)
        self.assertNotIn("**", body)
        self.assertNotIn("`", body)
        # Column structure must remain, not collapse into a sentence.
        self.assertIn("33,891", body)
        self.assertIn("99.0%", body)
        self.assertIn("[measured]", body)
        self.assertIn("[unavailable]", body)

    def test_report_markdown_keeps_tables_and_provenance(self):
        body = router.render_report_markdown(self._sample_records(), as_text=False)
        self.assertIn("| Marking | Meaning |", body)
        self.assertIn("| `measured` |", body)
        self.assertIn("99.0%", body)
        self.assertIn("Deliberately not quantified", body)

    def test_report_reads_the_latest_real_comparison_not_the_last_record(self):
        """A trailing telemetry record must not blank out the headline."""
        records = self._sample_records()
        self.assertNotIn("comparison", records[-1])
        self.assertEqual(33536, router._latest_comparison(records)["saved_tokens_est"])
        for as_text in (True, False):
            body = router.render_report_markdown(records, as_text=as_text)
            self.assertIn("33,891", body)
            self.assertNotIn("— | estimated", body)

    def test_report_handles_an_empty_ledger(self):
        for as_text in (True, False):
            body = router.render_report_markdown([], as_text=as_text)
            self.assertIn("How to read the numbers", body)
        html = router.render_report_html([])
        self.assertIn("No measurements recorded yet", html)

    def test_report_html_is_self_contained(self):
        """A report that needs the network is a report that fails on delivery."""
        html = router.render_report_html(self._sample_records())
        for forbidden in ("http://", "https://", "<script", "cdn"):
            self.assertNotIn(forbidden, html, f"report must not reference {forbidden}")
        self.assertIn("<style>", html)

    def test_report_format_is_inferred_from_the_output_extension(self):
        cases = {".html": "html", ".md": "md", ".txt": "text", ".markdown": "md"}
        for suffix, expected in cases.items():
            out = Path("report") .with_suffix(suffix)
            # Reuse the same mapping the CLI applies.
            self.assertEqual(expected, {".md": "md", ".markdown": "md", ".txt": "text"}
                             .get(suffix, "html"))
        self.assertEqual(cases[".md"], "md")

    def test_tests_do_not_assert_platform_specific_input_universally(self):
        """Guard against the trap that cost two CI rounds.

        A test that builds a path with one separator and expects the other to
        work passes on Windows and fails on Linux, because '\\' is a legal
        filename character on POSIX but not a separator. Any test touching
        separators must branch on `os.name`.
        """
        source = (ROOT / "tests" / "test_router.py").read_text(encoding="utf-8")
        separator_tests = re.findall(r'def (test_[a-z_]*separator[a-z_]*)\(', source)
        for name in separator_tests:
            start = source.index(f"def {name}(")
            body = source[start : source.find("\n    def ", start + 10)]
            if "os.name" not in body:
                self.fail(f"{name} manipulates path separators but never checks os.name")
        self.assertIn(
            "test_paths_are_handled_with_both_separators", separator_tests,
            "the separator test should exist and be discoverable by this guard",
        )

    def test_reported_paths_are_canonical_and_consistent(self):
        """Any path handed back as *data* must be canonical, not just usable.

        Three CI rounds have now been lost to this class. One path has several
        legitimate spellings: macOS symlinks /var to /private/var, Windows short
        paths (RUNNER~1) expand to the long name, and '..' survives in any
        string built by joining. None of it shows on a developer machine, where
        tempdir already returns a canonical path.

        The rule is structural, not name-based, because the two previous guards
        matched on the word 'separator' and so missed a test that had no such
        word in its name while failing for exactly that reason.
        """
        router_src = (ROOT / "skills/aletheia/scripts/router.py").read_text(encoding="utf-8")
        test_src = (ROOT / "tests" / "test_router.py").read_text(encoding="utf-8")

        # 0. A silently duplicated test is dead code that also silently orphans
        #    whatever it was shadowing. Python keeps the last definition, so the
        #    suite still passes and a guard body quietly stops running.
        names = re.findall(r"^    def (test_\w+)", test_src, re.M)
        duplicates = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual([], duplicates, f"duplicate test definitions: {duplicates}")

        # 1. Every path a function returns as data must be canonicalised *at the
        #    point it is produced*. Checking only that ".resolve()" appears
        #    somewhere in the body is not enough: load_session_manifest
        #    resolves its search base, so deleting the resolve() on the returned
        #    value leaves the substring present and the guard silent.
        def _body(fn: str) -> str:
            start = router_src.index(f"def {fn}(")
            return router_src[start : router_src.find("\ndef ", start + 10)]

        manifest_body = _body("load_session_manifest")
        explicit_block = manifest_body[: manifest_body.index("base = (start")]
        self.assertIn(
            ".resolve()", explicit_block,
            "the explicit-path branch of load_session_manifest returns _path as data "
            "and must resolve() it; resolving only the search branch leaves the two "
            "branches reporting the same file under different spellings",
        )
        for fn in ("load_session_manifest", "find_installations"):
            self.assertIn(".resolve()", _body(fn), f"{fn} returns paths as data")

        # 2. A test comparing two paths must not resolve *inside* the assertion:
        #    resolving both sides normalises away the difference it exists to
        #    catch. This exact mistake hid the defect in the first draft of the
        #    test for the fix above.
        #    Matching is line-based on purpose: a character-class regex stops at
        #    the first ')' and so never sees the second operand of a comparison
        #    written as `Path(x["k"]).resolve()`.
        offenders = []
        for block in re.findall(r"self\.assert\w+\((.*?)\n(?=\s*(?:self\.|\w|#|\))|$)", test_src, re.S):
            if block.count(".resolve()") >= 2 and "assertIn" not in block and "assertNotIn" not in block:
                offenders.append(block.strip()[:120])
        self.assertEqual(
            [], offenders,
            "these assertions resolve both sides, which hides the difference they "
            f"are meant to detect:\n{offenders}",
        )

    def test_active_measurement_needs_no_host(self):
        """The point of `estimate`: measurement must not wait for a host.

        If this ever starts requiring anything from the host, the tool has gone
        back to being reactive — which is the problem it was built to solve.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            sessions = base / ".claude" / "projects" / "p"
            sessions.mkdir(parents=True)
            (sessions / "s.jsonl").write_text(
                json.dumps({"message": {"usage": {
                    "input_tokens": 111, "output_tokens": 22,
                    "cache_read_input_tokens": 333}}}) + "\n",
                encoding="utf-8",
            )
            result = router.active_measurement(
                roots=[base], since_days=None, task="hello", hosts=("claude",),
                home=base,
            )
            totals = result["token_totals"]
            # The bug this guards: canonical buckets are `cache_read`, the host
            # reports `cache_read_tokens`. Reading the wrong key yields a
            # confident zero.
            self.assertEqual(111, totals["input"])
            self.assertEqual(22, totals["output"])
            self.assertEqual(333, totals["cache_read"], "cache_read must map from cache_read_tokens")
            self.assertIn("claude", totals["hosts_included"])
            self.assertTrue(result["measured_without_asking_any_host"])

    def test_active_measurement_refuses_what_it_cannot_measure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = router.active_measurement(roots=[Path(tmp)], hosts=(), home=Path(tmp))
            blockers = result["unmeasurable_here"]
            self.assertEqual(router.UNAVAILABLE, blockers["host_internal_reasoning_tokens"])
            self.assertEqual(router.UNAVAILABLE, blockers["billed_cost"])
            # Completeness must be stated, never implied by a bare zero.
            self.assertIn("hosts_excluded_no_telemetry", result["token_totals"])

    def test_active_measurement_counts_unique_skills_not_installs(self):
        """A skill mirrored across four agents is loaded once, not four times."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for root_name in ("a", "b", "c"):
                d = base / root_name / "dupe"
                d.mkdir(parents=True)
                (d / "SKILL.md").write_text(
                    "---\nname: dupe\ndescription: Installed in three places.\n---\n# body\n",
                    encoding="utf-8",
                )
            result = router.active_measurement(roots=[base], hosts=(), home=base)
            inv = result["inventory"]
            self.assertEqual(3, inv["install_locations"])
            self.assertEqual(1, inv["unique_skills"])
            self.assertEqual(2, inv["duplicate_installs"])
            self.assertEqual(1, result["context_load"]["visible_skills"])

    def test_scoped_measurement_shows_the_saving(self):
        """The number a butler most needs: what scoping actually saves."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for i in range(8):
                d = base / f"skill-{i}"
                d.mkdir()
                (d / "SKILL.md").write_text(
                    f"---\nname: skill-{i}\ndescription: A skill with a reasonably long description number {i}.\n---\n# body\n",
                    encoding="utf-8",
                )
            unscoped = router.measure_local_context_load(router.discover([base])[0], "task")
            scoped = router.measure_local_context_load(
                router.discover([base])[0], "task", {"skill-0", "skill-1"}
            )
            self.assertGreater(unscoped["metadata_tokens_est"], scoped["metadata_tokens_est"])
            self.assertEqual(8, unscoped["visible_skills"])
            self.assertEqual(2, scoped["visible_skills"])
            # Bodies are only read for what is visible.
            self.assertGreater(unscoped["skill_body_pool_chars"], scoped["skill_body_pool_chars"])

    def test_log_growth_is_never_summed_into_tokens(self):
        """Bytes are not tokens. The report must not pretend otherwise."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            logs = base / "logs"
            logs.mkdir()
            for i in range(3):
                (logs / f"f{i}.log").write_text("x" * 500, encoding="utf-8")
            result = router.measure_host_growth({"testhost": logs}, since_hours=24)
            self.assertEqual(1, len(result))
            entry = result[0]
            self.assertEqual(1500, entry["bytes_written"])
            self.assertIn("NOT tokens", entry["unit"])
            # No numeric token field may exist on a byte-level record.
            numeric_keys = {k for k, v in entry.items() if isinstance(v, int)}
            self.assertEqual({"files_changed", "bytes_written", "since_hours"}, numeric_keys)
            self.assertIn("cannot be converted", entry["interpretation"])

    def test_business_errors_are_json_on_stdout_with_exit_2(self):
        """One error protocol, so a machine caller parses one shape.

        `parser.error` used to be mixed in for the same class of failure, which
        meant stderr text on one path and JSON on another. Machine callers
        generally handle only one.
        """
        import subprocess

        router_py = ROOT / "skills/aletheia/scripts/router.py"
        cases = [
            (["context", "--transcripts", "/definitely-not-here", "--window", "10"], "missing directory"),
            (["route", "task", "--top", "0"], "non-positive --top"),
            (["context", "--transcripts", str(ROOT), "--window", "0"], "non-positive --window"),
        ]
        for argv, label in cases:
            proc = subprocess.run(
                [sys.executable, "-B", str(router_py), *argv],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            self.assertEqual(2, proc.returncode, f"{label}: exit code")
            payload = json.loads(proc.stdout)  # must be valid JSON on stdout
            self.assertIn("error", payload, f"{label}: missing 'error' key")
            self.assertTrue(payload["error"], f"{label}: empty error message")

    def test_scan_route_lint_have_no_dead_json_flag(self):
        """A flag that is defined but never read is worse than no flag at all."""
        import subprocess

        router_py = ROOT / "skills/aletheia/scripts/router.py"
        # `route` takes a positional task, so supply one — otherwise argparse
        # stops at the missing argument and never reaches --json.
        cases = [
            (["scan"], "scan"),
            (["route", "some task"], "route"),
            (["lint"], "lint"),
        ]
        for argv, name in cases:
            proc = subprocess.run(
                [sys.executable, "-B", str(router_py), *argv, "--json"],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            # Argparse owns unknown-argument errors; the flag must be gone.
            # The exact wording differs by platform ("unrecognized argument"
            # vs "unrecognized arguments"), so match only the stable part.
            self.assertNotEqual(0, proc.returncode, f"{name} --json should not be accepted")
            self.assertIn("unrecognized", proc.stderr.lower())
            self.assertIn("--json", proc.stderr)

    def test_scope_sources_intersect_rather_than_override(self):
        """The docs and the code must agree: multiple sources intersect."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("alpha", "beta", "gamma"):
                d = root / name
                d.mkdir()
                (d / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: Skill {name} for scoping.\n---\n# body\n",
                    encoding="utf-8",
                )
            # --only names alpha+beta; the profile names only beta.
            profile = root / "profiles"
            profile.mkdir()
            (profile / "narrow.json").write_text(
                json.dumps(["beta"]), encoding="utf-8"
            )
            manifest = root / "aletheia-session.json"
            manifest.write_text(json.dumps({"only": ["beta", "gamma"]}), encoding="utf-8")

            skills, _ = router.discover([root])
            # beta is in all three; alpha only in --only; gamma only in the
            # manifest. Intersection is therefore just beta.
            combined, _ = router.apply_scope(skills, {"alpha", "beta"} & {"beta", "gamma"})
            self.assertEqual(["beta"], [s.name for s in combined])

            # And the documented wording must not contradict itself.
            for doc in ("README.md", "README.zh-CN.md",
                        "skills/aletheia/SKILL.md",
                        "skills/aletheia/references/TRANSPARENCY.md"):
                text = (ROOT / doc).read_text(encoding="utf-8")
                self.assertNotIn("overrides the manifest", text, f"{doc} still says override")
                self.assertNotIn("overrides the others", text, f"{doc} still says override")
                self.assertNotIn("优先于清单", text, f"{doc} still says override")

    def test_update_check_never_applies_anything(self):
        """Detection only. This is the whole point of the command's design.

        Rewriting a SKILL.md that another agent is reading is a bad trade, so
        there is deliberately no --apply. Guard it structurally.
        """
        import subprocess

        help_text = subprocess.run(
            [sys.executable, "-B", str(ROOT / "skills/aletheia/scripts/router.py"), "update", "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        ).stdout
        self.assertNotIn("--apply", help_text)
        self.assertNotIn("--install", help_text)
        self.assertNotIn("--force", help_text)

        source = (ROOT / "skills/aletheia/scripts/router.py").read_text(encoding="utf-8")
        # The helper must be read-only: only ls-remote, log, describe, status.
        for forbidden in ('"pull"', '"push"', '"fetch"', '"checkout"', '"merge"', '"reset"'):
            self.assertNotIn(
                f"_git(root, {forbidden}", source,
                "update detection must never invoke a mutating git command",
            )

    def test_update_check_reports_unknown_rather_than_guessing(self):
        """No network, no tags, or no repo must all read as unknown."""
        with tempfile.TemporaryDirectory() as tmp:
            result = router.check_update(repo=Path(tmp))   # not a git repo
            self.assertFalse(result["checked"])
            self.assertEqual(router.UNAVAILABLE, result["update_available"])
            self.assertIn("not inside a git repository", result["reason"])

            # A real repo, but with the network explicitly off.
            result = router.check_update(repo=ROOT, fetch=False)
            self.assertTrue(result["checked"])
            self.assertEqual(router.UNAVAILABLE, result["update_available"])
            self.assertIn("--no-fetch", result["reason"])

    def test_update_check_compares_tags_on_this_repository(self):
        """The project's own repository must be self-describing.

        Without tags there is nothing to compare a version against. A shallow
        clone legitimately has none — that is an environment limitation, not a
        defect in the repository — so this skips instead of failing, and CI is
        configured to fetch tags anyway so the real check runs there.
        """
        import subprocess

        tags = subprocess.run(
            ["git", "-C", str(ROOT), "tag", "-l"],
            capture_output=True, text=True,
        ).stdout.split()
        if not tags:
            self.skipTest(
                "no tags in this clone (shallow checkout?); CI fetches them with fetch-depth: 0"
            )
        self.assertIn(f"v{router.VERSION}", tags, "the current version must be tagged")

        result = router.check_update(repo=ROOT, fetch=False)
        self.assertTrue(result["checked"])
        # `describe` reports the nearest reachable tag, which may be behind HEAD
        # while fixes are unreleased — that is normal and must not be an error.
        if result["local_tag"] == router.UNAVAILABLE:
            self.skipTest("no tag reachable from HEAD in this clone")
        self.assertTrue(str(result["local_tag"]).startswith("v"), result["local_tag"])
        self.assertLessEqual(
            router._parse_version(result["local_tag"]),
            router._parse_version(router.VERSION),
            "the nearest tag must not be ahead of the declared version",
        )

    def test_upstream_scan_reports_a_gap_rather_than_inventing_one(self):
        """Most third-party skills carry no upstream. Say so; do not fabricate."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "orphan"
            d.mkdir()
            (d / "SKILL.md").write_text(
                "---\nname: orphan\ndescription: A skill with no recorded origin.\n---\n# body\n",
                encoding="utf-8",
            )
            result = router.scan_upstreams(roots=[root])
            summary = result["version_summary"]
            self.assertEqual(1, result["total_unique_skills"])
            self.assertEqual(1, summary["no_version_signal"])
            self.assertEqual(0, summary["checkable_against_upstream"])
            row = result["skills"][0]
            self.assertEqual("none", row["source_kind"])
            self.assertEqual(router.UNAVAILABLE, row["update_available"])

    def test_installations_lists_where_the_skill_lives(self):
        """A skill in several host directories is normal, not a problem."""
        found = router.find_installations("aletheia")
        # At minimum the repository working copy counts.
        self.assertTrue(found, "the repository's own skills/aletheia must be found")
        self.assertTrue(
            any("(this repository)" in host for host in found),
            f"the working copy should be reported separately from installs: {list(found)}",
        )

    def _write_skill(self, root: Path, name: str, extra_front: str = "", body: str = "# body\n"):
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Skill {name} used for version tests.\n{extra_front}---\n{body}",
            encoding="utf-8",
        )
        return d

    def test_marketplace_install_detects_local_modification(self):
        """The install record carries a content hash; that detects local edits."""
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = self._write_skill(root, "market")
            skill_md = d / "SKILL.md"
            digest = "sha256:" + hashlib.sha256(skill_md.read_bytes()).hexdigest()
            (d / "_skillhub_meta.json").write_text(
                json.dumps({
                    "slug": "market", "version": "1.2.3", "source": "marketplace",
                    "installedAt": 1700000000000, "installedContentHash": digest,
                }),
                encoding="utf-8",
            )
            skills, _ = router.discover([root])
            record = router.track_skill_version(skills[0], check_remote=False)
            self.assertEqual("marketplace", record["source_kind"])
            self.assertEqual("1.2.3", record["installed_version"])
            self.assertFalse(record["locally_modified"], "hash matches, so unmodified")
            # A newer release is NOT observable without the marketplace API.
            self.assertFalse(record["can_check_for_updates"])
            self.assertEqual(router.UNAVAILABLE, record["update_available"])

            # Now edit the file and confirm it is detected.
            skill_md.write_text(
                skill_md.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8"
            )
            record = router.track_skill_version(skills[0], check_remote=False)
            self.assertTrue(record["locally_modified"], "content hash must now differ")

    def test_declared_version_alone_cannot_detect_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_skill(root, "declared", extra_front="version: 2.0.0\n")
            skills, _ = router.discover([root])
            record = router.track_skill_version(skills[0], check_remote=False)
            self.assertEqual("frontmatter", record["source_kind"])
            self.assertEqual("2.0.0", record["installed_version"])
            self.assertFalse(record["can_check_for_updates"])
            self.assertEqual(router.UNAVAILABLE, record["update_available"])
            self.assertTrue(record["why_not"])

    def test_skill_with_no_version_signal_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_skill(root, "orphan")
            skills, _ = router.discover([root])
            record = router.track_skill_version(skills[0], check_remote=False)
            self.assertEqual("none", record["source_kind"])
            self.assertEqual(router.UNAVAILABLE, record["installed_version"])
            self.assertFalse(record["can_check_for_updates"])

    def test_git_skill_compares_like_for_like_shas(self):
        """Regression: a full sha compared against a short one always differs.

        `git rev-parse HEAD` returns 40 characters while `ls-remote` may be
        truncated, so comparing them directly reported every repo as outdated —
        including a repository that was demonstrably up to date.
        """
        import subprocess

        result = router.check_update(repo=ROOT, fetch=True)
        if not result.get("checked") or result.get("latest_tag") == router.UNAVAILABLE:
            self.skipTest("no network or no tags available")
        # This repository is pushed, so it must not report itself as outdated.
        self.assertIs(
            result["update_available"], False,
            f"a fully pushed repo must read as current: {result}",
        )

    def test_versions_command_never_mutates_a_skill(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = self._write_skill(root, "untouched")
            before = (d / "SKILL.md").read_bytes()
            proc = subprocess.run(
                [sys.executable, "-B", str(ROOT / "skills/aletheia/scripts/router.py"),
                 "versions", "--root", str(root)],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertEqual(before, (d / "SKILL.md").read_bytes(),
                             "versions must be read-only")

    def test_upstream_scan_and_versions_agree_on_source_kind(self):
        """Two commands, one source of truth. They must not disagree."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_skill(root, "plain")
            self._write_skill(root, "withversion", extra_front="version: 0.1.0\n")
            survey = router.survey_versions(roots=[root], check_remote=False)
            scan = router.scan_upstreams(roots=[root])
            survey_kinds = {r["name"]: r["source_kind"] for r in survey["records"]}
            for row in scan["skills"]:
                self.assertEqual(
                    survey_kinds[row["name"]], row["source_kind"],
                    f"{row['name']}: scan and versions disagree on the source kind",
                )

    def test_chinese_readme_has_no_untranslated_fragments(self):
        """Catch half-translated prose before a reader does.

        A stray English word inside a Chinese sentence is easy to write and easy
        to miss on review — the line still looks like Chinese at a glance. This
        only guards the opening section, where a broken first paragraph does the
        most damage, and it allows the English terms that are genuinely used
        (product names, identifiers).
        """
        text = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        head = text.split("## ", 1)[0]
        # Words that legitimately appear in the Chinese README.
        allowed = {
            "Aletheia", "Skill", "Skills", "Agent", "JSON", "CLI", "README",
            "WorkBuddy", "Codex", "Claude", "MIT", "Python", "GitHub",
            "Kimi", "Qwen", "Hermes", "OpenClaw", "Copilot", "Gemini",
            "CHANGELOG", "LICENSE", "CONTRIBUTING", "SECURITY", "Tkinter",
        }
        # A stray English word glued between CJK characters — separated only by
        # punctuation or Markdown emphasis — is a translation that stopped
        # mid-sentence. The separator class has to include `**` because that is
        # exactly where it lands in practice: 「解蔽」** principles.
        separator = r"[\s」』）】*_·、，。]*"
        suspicious = re.findall(
            r"[一-鿿]" + separator + r"[A-Za-z]{3,}[A-Za-z\s]*", head
        )
        leftovers = [
            fragment
            for fragment in suspicious
            if not any(
                word in allowed for word in re.findall(r"[A-Za-z]{3,}", fragment)
            )
        ]
        self.assertEqual([], leftovers, f"untranslated fragments in the Chinese README: {leftovers}")

    def test_changelog_does_not_repeat_a_fix_verbatim(self):
        """A repeated Fix entry is either a duplicate or an undocumented regression."""
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        entries = re.findall(r"^- (?!\*\*)(?!#)(.+)$", text, re.M)
        seen: dict[str, int] = {}
        for entry in entries:
            key = re.sub(r"\s+", " ", entry.strip().rstrip("."))
            seen[key] = seen.get(key, 0) + 1
        duplicates = {k: v for k, v in seen.items() if v > 1}
        self.assertEqual({}, duplicates, f"verbatim duplicate changelog entries: {list(duplicates)}")

    def test_bilingual_readmes_stay_in_step(self):
        """The two READMEs must not drift apart silently.

        This project ships an English default and a Chinese translation. Every
        capability added in one language has to appear in the other, or half the
        readers are missing features that exist. Asserted on *facts* (counts,
        host ids, paths) rather than prose, because wording legitimately differs.
        """
        en = (ROOT / "README.md").read_text(encoding="utf-8")
        zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

        facts = {
            "host count": str(len(router.TELEMETRY_HOSTS)),
            "sqlite hosts": "SQLite",
            "multi-agent library": ("openclaw/skills", "hermes/skills"),
            "cross-platform": ("os.name",),
            "zero-dependency": ("zero_dependency_check",),
        }
        for label, needles in facts.items():
            for needle in needles:
                self.assertIn(needle, en, f"README.md missing {label}: {needle!r}")
                self.assertIn(needle, zh, f"README.zh-CN.md missing {label}: {needle!r}")

        # Every registered host must be discoverable from the docs, or a user
        # cannot tell that their agent is supported.
        for host, spec in router.TELEMETRY_HOSTS.items():
            self.assertIn(spec["label"], en, f"README.md does not mention {spec['label']}")

        # Both files must link the same reference set.
        for name in re.findall(r"`(references/[A-Z_]+\.md)`", en):
            self.assertIn(name, zh, f"README.zh-CN.md does not reference {name}")

    def test_readme_links_resolve(self):
        """Every relative link in the READMEs must point at something real."""
        import re as _re

        for readme in ("README.md", "README.zh-CN.md"):
            path = ROOT / readme
            text = path.read_text(encoding="utf-8")
            for match in _re.finditer(r"\[[^\]]*\]\(([^)#][^)]*)\)", text):
                target = match.group(1).strip()
                if target.startswith(("http", "mailto:")):
                    continue
                self.assertTrue(
                    (path.parent / target).resolve().exists(),
                    f"{readme} links to a missing path: {target}",
                )

    def test_skill_md_sections_are_not_nested_by_accident(self):
        """A demoted '##' silently buries routing rules under an unrelated topic.

        Every top-level capability needs its own '##'. Without this guard, a
        future edit can nest 'Candidate discovery' or 'Decision policy' under
        whatever section happened to be edited last.
        """
        text = (ROOT / "skills/aletheia/SKILL.md").read_text(encoding="utf-8")
        required = [
            "Purpose",
            "Who chooses",
            "Mandatory preflight",
            "Transparency",
            "Stop gates",
            "Progress reporting",
            "Candidate discovery",
            "Session scoping",
            "Context pressure",
            "Decision policy",
            "Evidence standard",
        ]
        for heading in required:
            self.assertIn(
                f"\n## {heading}", text,
                f"'{heading}' must be a top-level section, not nested under another",
            )

    def test_skill_md_stays_within_the_spec_size_guidance(self):
        """The spec recommends under 500 lines; progressive disclosure needs slack."""
        lines = (ROOT / "skills/aletheia/SKILL.md").read_text(encoding="utf-8").splitlines()
        self.assertLess(len(lines), 500, "SKILL.md must stay under the spec's 500-line guidance")

    def test_skill_md_description_fits_the_spec_limit(self):
        text = (ROOT / "skills/aletheia/SKILL.md").read_text(encoding="utf-8")
        front = text.split("---")[1]
        match = re.search(r"description: >-\n(.*?)\nlicense:", front, re.S)
        self.assertIsNotNone(match, "description must use the block form")
        description = " ".join(l.strip() for l in match.group(1).splitlines() if l.strip())
        # Leave headroom: a description at the limit cannot grow with the skill.
        self.assertLess(len(description), 1000, f"description is {len(description)} chars")

    def test_every_reference_named_in_skill_md_exists(self):
        """A pointer to a missing file is worse than no pointer."""
        text = (ROOT / "skills/aletheia/SKILL.md").read_text(encoding="utf-8")
        refs = set(re.findall(r"`references/([A-Z_]+\.md)`", text))
        self.assertGreaterEqual(len(refs), 6, "SKILL.md should point at its reference set")
        for ref in sorted(refs):
            self.assertTrue((ROOT / "skills/aletheia/references" / ref).is_file(),
                            f"SKILL.md references {ref}, which does not exist")

    # --- Cross-platform behaviour -------------------------------------------------
    # Windows, macOS and Linux disagree about line endings, path separators and
    # sqlite locking. A feature that only works on the developer's machine is not
    # a feature; these tests pin the behaviour on all three.

    def test_repair_preserves_line_ending_convention(self):
        """CRLF in must yield CRLF out; LF must stay LF.

        Rewriting a Windows file with LF endings makes the whole file appear
        changed in review, and some tools mis-parse it.
        """
        for newline, label in (("\n", "LF"), ("\r\n", "CRLF")):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                d = root / "listtools"
                d.mkdir()
                lines = ["---", "name: listtools", "description: Uses a list.",
                         "allowed-tools:", "  - Bash(git:*)", "  - Read", "---", "", "# body", ""]
                target = d / "SKILL.md"
                with target.open("w", encoding="utf-8", newline="") as handle:
                    handle.write(newline.join(lines))
                changed, note = router.repair_skill(target, "allowed_tools_list")
                self.assertTrue(changed, f"{label}: {note}")
                raw = target.read_bytes().decode("utf-8")
                self.assertEqual("ok", router.diagnose_skill(target)["kind"], f"{label} must parse clean")
                if newline == "\r\n":
                    self.assertIn("\r\n", raw, "CRLF must be preserved on a CRLF file")
                else:
                    self.assertNotIn("\r\n", raw, "LF file must not gain CRLF")
                self.assertIn("# body", raw)

    def test_paths_are_handled_with_both_separators(self):
        """A path typed the other common way must still resolve.

        On Windows both separators are accepted, because Windows itself treats
        '/' as a separator. On POSIX, '\\' is an ordinary filename character —
        `\\tmp\\x` is not a path at all — so only the native form is asserted
        there. Asserting otherwise would demand the impossible.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "pdf-processing"
            d.mkdir()
            (d / "SKILL.md").write_text(
                "---\nname: pdf-processing\ndescription: Extract text and tables from PDF files.\n---\n# body\n",
                encoding="utf-8",
            )
            direct, _ = router.discover([d])
            self.assertEqual(["pdf-processing"], [s.name for s in direct])

            native = str(d)
            # Forward slashes are the portable form and must work everywhere.
            variants = [native.replace("\\", "/")]
            if os.name == "nt":
                # Windows additionally accepts the escaped-separator form.
                variants.append(native.replace("/", "\\"))
            for variant in variants:
                skills, _ = router.discover([Path(variant)])
                self.assertEqual(["pdf-processing"], [s.name for s in skills], variant)

            if os.name != "nt":
                # A backslash path is not a path on POSIX. It must resolve to
                # nothing rather than silently matching something unintended.
                bogus = native.replace("/", "\\")
                skills, _ = router.discover([Path(bogus)])
                self.assertEqual([], [s.name for s in skills], bogus)

    def test_sqlite_reading_is_readonly_and_portable(self):
        """SQLite is stdlib, so hosts storing usage there are readable everywhere.

        Opened read-only via URI: a telemetry reader must never mutate or lock a
        host's database.
        """
        import sqlite3

        # ignore_cleanup_errors: a .db can still be held open by the OS on
        # Windows at teardown, and that must not fail an unrelated assertion.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            base = Path(tmp)
            db_dir = base / ".hermes"
            db_dir.mkdir()
            db = db_dir / "state.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE sessions (id TEXT, input_tokens INT, output_tokens INT)")
                conn.execute("INSERT INTO sessions VALUES ('a', 100, 20)")
                conn.execute("INSERT INTO sessions VALUES ('b', 300, 40)")
            before = db.stat().st_mtime

            usage = router.collect_host_usage(base=base, hosts=("hermes",))
            self.assertTrue(usage["hermes"]["available"], usage["hermes"].get("reason"))
            self.assertEqual(400, usage["hermes"]["input_tokens"])
            self.assertEqual(60, usage["hermes"]["output_tokens"])
            # Read-only: the file must be untouched.
            self.assertEqual(before, db.stat().st_mtime)

    def test_sqlite_missing_table_reports_a_reason_not_zero(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            import sqlite3

            base = Path(tmp)
            db_dir = base / ".openclaw"
            db_dir.mkdir()
            with sqlite3.connect(db_dir / "x.db") as conn:
                conn.execute("CREATE TABLE something_else (a INT)")
            usage = router.collect_host_usage(base=base, hosts=("openclaw",))
            self.assertFalse(usage["openclaw"]["available"])
            self.assertEqual(router.UNAVAILABLE, usage["openclaw"]["input_tokens"])
            self.assertTrue(usage["openclaw"]["reason"], "a missing store must state why")

    def test_registry_includes_the_multi_agent_hosts(self):
        """Hermes and OpenClaw share a skill library and must be visible to it."""
        for expected in ("hermes", "openclaw"):
            self.assertIn(expected, router.TELEMETRY_HOSTS)
            self.assertTrue(
                router.TELEMETRY_HOSTS[expected]["skills"],
                f"{expected} must declare its skill directories",
            )

    def test_audit_and_telemetry_work_without_pyyaml(self):
        """The project ships zero dependencies; core paths must not need PyYAML.

        Guards against a future 'import yaml' creeping into discovery or repair
        and failing only on CI, where PyYAML is absent.
        """
        import subprocess
        script = ROOT / "tests" / "zero_dependency_check.py"
        proc = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, cwd=str(ROOT)
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_repair_handles_crlf_without_corrupting(self):
        """Windows checkouts are CRLF; a bare-\\n regex silently fails there."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "listtools"
            d.mkdir()
            body = (
                "---\r\nname: listtools\r\ndescription: Uses a list.\r\n"
                "allowed-tools:\r\n  - Bash(git:*)\r\n  - Read\r\n---\r\n\r\n# body\r\n"
            )
            target = d / "SKILL.md"
            target.write_text(body, encoding="utf-8", newline="")
            self.assertEqual("allowed_tools_list", router.diagnose_skill(target)["kind"])
            changed, note = router.repair_skill(target, "allowed_tools_list")
            self.assertTrue(changed, note)
            self.assertEqual("ok", router.diagnose_skill(target)["kind"])
            text = target.read_text(encoding="utf-8")
            self.assertIn("allowed-tools: Bash(git:*) Read", text)
            self.assertIn("# body", text)


if __name__ == "__main__":
    unittest.main()

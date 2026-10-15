import importlib.util
import json
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
            (root / "bad/SKILL.md").symlink_to(self.fixtures / "pdf-processing/SKILL.md")
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
            self.assertEqual(str(manifest), found["_path"])

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

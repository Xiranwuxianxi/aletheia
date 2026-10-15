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


if __name__ == "__main__":
    unittest.main()

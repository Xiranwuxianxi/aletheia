"""Tests for the owner-controlled hard-injection hook.

Two surfaces are covered:

* ``router.hook_settings`` / ``save_hook_settings`` — the resolution chain that
  keeps the owner in control (nearest declaration wins, nothing is hardwired).
* ``hook_prompt_submit.py`` end to end — the script a host's hook runtime calls:
  session-start bootstraps the first turn of a conversation, prompt-submit
  injects candidates, and a disabled hook is a true no-op.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "skills/aletheia/scripts/router.py"
HOOK = ROOT / "skills/aletheia/scripts/hook_prompt_submit.py"
spec = importlib.util.spec_from_file_location("skill_router_hook_tests", ROUTER)
router = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = router
spec.loader.exec_module(router)


class HookSettingsTests(unittest.TestCase):
    def _tree(self, tmp):
        home = Path(tmp) / "home"
        project = Path(tmp) / "work" / "repo"
        project.mkdir(parents=True)
        home.mkdir()
        return home, project

    def _write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_defaults_when_nothing_declares_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, project = self._tree(tmp)
            s = router.hook_settings(cwd=project, home=home)
            self.assertTrue(s["enabled"])
            self.assertEqual(list(router.HOOK_EVENTS), s["events"])
            self.assertEqual("default", s["sources"]["enabled"])
            self.assertEqual("default", s["sources"]["events"])

    def test_machine_level_switch_is_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, project = self._tree(tmp)
            self._write(home / ".aletheia" / "config.json", {"hook": "off"})
            s = router.hook_settings(cwd=project, home=home)
            self.assertFalse(s["enabled"])
            self.assertTrue(s["sources"]["enabled"].startswith("machine:"))

    def test_nearest_declaration_wins_and_levels_do_not_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, project = self._tree(tmp)
            self._write(home / ".aletheia" / "config.json", {"hook": "off"})
            self._write(project / "aletheia-config.json", {"mode": "manual"})
            s = router.hook_settings(cwd=project, home=home)
            # The project file declares only `mode`, so it must not silently
            # re-enable a hook the owner switched off machine-wide.
            self.assertFalse(s["enabled"])
            # But a project that DOES declare it wins over the machine default.
            self._write(project / "aletheia-config.json", {"mode": "manual", "hook": "on"})
            s = router.hook_settings(cwd=project, home=home)
            self.assertTrue(s["enabled"])
            self.assertTrue(s["sources"]["enabled"].startswith("project:"))
            # And the per-session manifest beats the project file.
            self._write(project / "aletheia-session.json", {"only": ["pdf"], "hook": "off"})
            s = router.hook_settings(cwd=project, home=home)
            self.assertFalse(s["enabled"])
            self.assertTrue(s["sources"]["enabled"].startswith("session:"))

    def test_events_can_be_narrowed_without_touching_the_switch(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, project = self._tree(tmp)
            self._write(project / "aletheia-config.json", {"hook_events": "session-start"})
            s = router.hook_settings(cwd=project, home=home)
            self.assertTrue(s["enabled"])  # untouched by an events-only declaration
            self.assertEqual(["session-start"], s["events"])
            self.assertEqual("default", s["sources"]["enabled"])

    def test_explicit_config_beats_every_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, project = self._tree(tmp)
            self._write(home / ".aletheia" / "config.json", {"hook": "on"})
            explicit = Path(tmp) / "forced.json"
            self._write(explicit, {"hook": "off"})
            os.environ["ALETHEIA_HOOK_CONFIG"] = str(explicit)
            try:
                s = router.hook_settings(cwd=project, home=home)
            finally:
                del os.environ["ALETHEIA_HOOK_CONFIG"]
            self.assertFalse(s["enabled"])
            self.assertTrue(s["sources"]["enabled"].startswith("explicit:"))

    def test_save_merges_and_never_clobbers_other_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "aletheia-config.json"
            self._write(cfg, {"mode": "manual", "only": ["pdf"]})
            router.save_hook_settings(cfg, enabled=False, events="session-start")
            data = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual("off", data["hook"])
            self.assertEqual(["session-start"], data["hook_events"])
            self.assertEqual("manual", data["mode"])
            self.assertEqual(["pdf"], data["only"])
            # ...and the mode writer returns the favour: it used to rewrite the
            # whole file as {"mode": ...}, silently erasing hook preferences.
            proc = subprocess.run(
                [sys.executable, str(ROUTER), "mode", "--config", str(cfg), "--set", "auto"],
                capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            saved = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual("auto", saved["mode"])
            self.assertEqual("off", saved["hook"])
            self.assertEqual(["session-start"], saved["hook_events"])

    def test_unknown_events_are_rejected_not_guessed(self):
        self.assertEqual(("session-start",), router.parse_hook_events("session-start"))
        self.assertEqual(("session-start", "prompt-submit"),
                         router.parse_hook_events("session-start,prompt-submit"))
        self.assertEqual((), router.parse_hook_events(""))
        self.assertIsNone(router.parse_hook_events("bogus"))
        self.assertIsNone(router.parse_hook_events(["session-start", "bogus"]))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(router.SkillError):
                router.save_hook_settings(Path(tmp) / "c.json", events="bogus")


class HookScriptTests(unittest.TestCase):
    def run_hook(self, payload: dict | None, config: dict | None = None,
                 argv: tuple = ()) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env["ALETHEIA_HOOK_CACHE"] = str(Path(tmp) / "cache.json")
            # Hermetic retrieval: the bundled fixtures guarantee a candidate on
            # every machine, including CI where no real host library exists.
            env["SKILL_PATHS"] = str(ROOT / "tests/fixtures")
            if config is not None:
                cfg = Path(tmp) / "config.json"
                cfg.write_text(json.dumps(config), encoding="utf-8")
                env["ALETHEIA_HOOK_CONFIG"] = str(cfg)
            else:
                env.pop("ALETHEIA_HOOK_CONFIG", None)
            proc = subprocess.run(
                [sys.executable, str(HOOK), *argv],
                input=json.dumps(payload) if payload is not None else "",
                capture_output=True, text=True, env=env, timeout=120,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            return proc.stdout

    def envelope(self, out: str) -> dict:
        self.assertTrue(out.strip(), "expected an injected envelope, got silence")
        data = json.loads(out)
        self.assertTrue(data["continue"])
        self.assertIn("additionalContext", data["hookSpecificOutput"])
        return data

    def test_session_start_bootstraps_the_first_turn(self):
        out = self.run_hook({"hook_event_name": "SessionStart", "source": "startup",
                             "cwd": str(ROOT)})
        data = self.envelope(out)
        self.assertEqual("SessionStart", data["hookSpecificOutput"]["hookEventName"])
        text = data["hookSpecificOutput"]["additionalContext"]
        self.assertIn("session start", text)
        self.assertIn("router.py route", text)  # primes the preflight
        self.assertIn("SKILL.md", text)

    def test_prompt_submit_injects_candidates_for_this_prompt(self):
        out = self.run_hook({"hook_event_name": "UserPromptSubmit",
                             "prompt": "把这份 PDF 转成一份精炼报告",
                             "cwd": str(ROOT)})
        data = self.envelope(out)
        self.assertEqual("UserPromptSubmit", data["hookSpecificOutput"]["hookEventName"])
        text = data["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Skill library snapshot", text)  # retrieval really ran
        self.assertIn("Advisory candidates", text)     # and produced candidates
        self.assertIn("SKILL.md", text)

    def test_owner_off_is_a_true_noop(self):
        out = self.run_hook({"hook_event_name": "UserPromptSubmit", "prompt": "hi",
                             "cwd": str(ROOT)}, config={"hook": "off"})
        self.assertEqual("", out.strip(), "a disabled hook must add nothing")

    def test_event_filtering_is_silent_for_the_muted_event(self):
        out = self.run_hook({"hook_event_name": "UserPromptSubmit", "prompt": "hi",
                             "cwd": str(ROOT)},
                            config={"hook": "on", "hook_events": "session-start"})
        self.assertEqual("", out.strip())
        out = self.run_hook({"hook_event_name": "SessionStart", "cwd": str(ROOT)},
                            config={"hook": "on", "hook_events": "session-start"})
        self.envelope(out)

    def test_prompt_text_is_never_echoed(self):
        marker = "S3CRET-MARKER-DO-NOT-LEAK"
        out = self.run_hook({"hook_event_name": "UserPromptSubmit",
                             "prompt": f"hide this {marker} please",
                             "cwd": str(ROOT)})
        self.assertNotIn(marker, out)

    def test_manual_mode_is_respected_and_announced(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "aletheia-config.json"
            cfg.write_text(json.dumps({"mode": "manual"}), encoding="utf-8")
            out = self.run_hook({"hook_event_name": "SessionStart",
                                 "cwd": str(cfg.parent)})
            text = self.envelope(out)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("manual", text)
            self.assertIn("wait for the owner", text)

    def test_empty_prompt_still_injects_the_protocol(self):
        out = self.run_hook({}, argv=("--event", "prompt-submit"))
        text = self.envelope(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("five stages", text)
        self.assertNotIn("Advisory candidates", text)  # nothing to route on

    def test_unlabeled_event_without_a_prompt_is_silent(self):
        # A host that labels nothing and sends no prompt field proves nothing;
        # guessing would inject noise, so the hook stays quiet.
        out = self.run_hook({"cwd": str(ROOT)})
        self.assertEqual("", out.strip())


if __name__ == "__main__":
    unittest.main()

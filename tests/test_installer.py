import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts/install.py"


class InstallerTests(unittest.TestCase):
    def run_install(self, *args):
        proc = subprocess.run(
            [sys.executable, str(INSTALL), *map(str, args)],
            capture_output=True, text=True,
        )
        return proc

    def payload(self, *args):
        """Run and parse. The installer prints JSON on success by contract."""
        proc = self.run_install(*args)
        self.assertEqual(0, proc.returncode, proc.stderr)
        return json.loads(proc.stdout)

    def test_install_bootstrap_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("My existing agent rules.\n", encoding="utf-8")
            args = ("--host", "codex", "--scope", "project", "--project", root, "--bootstrap")

            dry = self.payload(*args, "--dry-run")
            self.assertFalse((root / ".agents").exists(), "dry-run must not write")
            self.assertIn("would_bootstrap", json.dumps(dry))

            result = self.payload(*args)
            self.assertTrue((root / ".agents/skills/aletheia/SKILL.md").is_file())
            agents = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("My existing agent rules.", agents, "existing content must survive")

            self.payload(*args)
            agents_again = (root / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(1, agents_again.count("BEGIN ALETHEIA BOOTSTRAP"),
                             "re-running must not duplicate the block")
            self.assertIn("My existing agent rules.", agents_again)

    def test_existing_different_install_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".agents/skills/aletheia"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("previous", encoding="utf-8")

            out = self.run_install("--host", "codex", "--scope", "project", "--project", root)
            self.assertNotEqual(0, out.returncode)
            self.assertEqual("previous", (skill / "SKILL.md").read_text(encoding="utf-8"),
                             "a refusal must leave the file untouched")

            forced = self.payload("--host", "codex", "--scope", "project", "--project", root, "--force")
            self.assertTrue((skill / "SKILL.md").is_file())
            self.assertTrue(any(skill.parent.glob("aletheia.backup-*/SKILL.md")),
                            "the previous install must be backed up, never deleted")
            self.assertIn("backup", json.dumps(forced))

    def test_identity_files_are_never_written(self):
        """SOUL.md and friends describe the user, not the routing policy.

        A host may name one of these as its instruction file. Writing a routing
        hook there would overwrite a persona, which is not a recoverable mistake
        and not what this tool is for.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            soul = root / "SOUL.md"
            soul.write_text("I am the user's persona.\n", encoding="utf-8")
            proc = self.run_install("--scope", "user", "--home", root, "--bootstrap", "--host", "hermes")
            # Whatever it decides to do, the persona file must be byte-identical.
            self.assertEqual("I am the user's persona.\n", soul.read_text(encoding="utf-8"))

    def test_a_shared_directory_is_installed_once(self):
        """~/.agents/skills is claimed by six hosts; one copy, one hook."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.payload("--scope", "user", "--home", root)
            installs = [a for a in data["actions"] if a.get("operation") == "installed"]
            targets = [a["target"] for a in installs]
            self.assertEqual(len(targets), len(set(targets)),
                             f"the same directory installed twice: {targets}")

    def test_a_host_without_an_instruction_file_gets_the_skill_and_says_so(self):
        """No verified filename means no guess — and a stated reason."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.payload("--scope", "user", "--home", root, "--bootstrap",
                                "--host", "openclaw")
            reasons = [a for a in data["actions"] if a.get("operation") == "bootstrap_skipped"]
            self.assertTrue(reasons, "a host with no verified instruction file must say so")
            self.assertIn("no verified instruction file", reasons[0]["reason"])

    def test_every_registered_host_has_an_install_path(self):
        """The old installer knew two hosts while the registry tracked fourteen."""
        data = self.payload("--list")
        listed = {h["key"] for h in data["hosts"]}
        spec = subprocess.run(
            [sys.executable, "-B", "-c",
             "import importlib.util,pathlib,sys,json;"
             "s=importlib.util.spec_from_file_location('r','skills/aletheia/scripts/router.py');"
             "m=importlib.util.module_from_spec(s);sys.modules['r']=m;s.loader.exec_module(m);"
             "print(json.dumps(sorted(m.TELEMETRY_HOSTS)))"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        registry = set(json.loads(spec.stdout))
        self.assertEqual(registry, listed,
                         "a host in the registry with no install path is invisible to users")

    def test_user_scope_writes_only_under_the_given_home(self):
        """A unit test must never touch the developer's real home directory.

        This was not hypothetical: an earlier version of this suite ran the user
        scope against the real home and created ~/.hermes.md as a side effect.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_home = Path.home()
            marker = real_home / ".hermes.md"
            before = marker.read_bytes() if marker.is_file() else None
            self.payload("--scope", "user", "--home", root, "--bootstrap")
            after = marker.read_bytes() if marker.is_file() else None
            self.assertEqual(before, after,
                             "the installer wrote outside the --home directory")

    def test_unknown_host_is_rejected_by_name(self):
        out = self.run_install("--host", "definitely-not-a-host", "--scope", "user",
                               "--home", str(Path(tempfile.gettempdir())))
        self.assertNotEqual(0, out.returncode)
        self.assertIn("unknown host", (out.stderr + out.stdout).lower())


if __name__ == "__main__":
    unittest.main()
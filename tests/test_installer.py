import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts/install.py"


class InstallerTests(unittest.TestCase):
    def run_install(self, *args):
        return subprocess.run([sys.executable, str(INSTALL), *map(str, args)], capture_output=True, text=True)

    def test_install_bootstrap_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("My existing agent rules.\n", encoding="utf-8")
            args = ("--platform", "both", "--scope", "project", "--project", root, "--bootstrap")
            dry = self.run_install(*args, "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertFalse((root / ".agents").exists())
            self.assertIn("would_bootstrap", dry.stdout)
            result = self.run_install(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / ".agents/skills/aletheia/SKILL.md").is_file())
            self.assertTrue((root / ".claude/skills/aletheia/SKILL.md").is_file())
            self.assertIn("My existing agent rules.", (root / "AGENTS.md").read_text(encoding="utf-8"))
            result2 = self.run_install(*args)
            self.assertEqual(result2.returncode, 0, result2.stderr)
            self.assertEqual(1, (root / "AGENTS.md").read_text(encoding="utf-8").count("BEGIN ALETHEIA BOOTSTRAP"))

    def test_existing_different_install_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / ".agents/skills/aletheia"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("previous", encoding="utf-8")
            out = self.run_install("--platform", "codex", "--project", root)
            self.assertNotEqual(0, out.returncode)
            self.assertEqual("previous", (skill / "SKILL.md").read_text(encoding="utf-8"))
            forced = self.run_install("--platform", "codex", "--project", root, "--force")
            self.assertEqual(0, forced.returncode, forced.stderr)
            self.assertTrue((skill / "SKILL.md").is_file())
            self.assertTrue(any(skill.parent.glob("aletheia.backup-*/SKILL.md")))


if __name__ == "__main__":
    unittest.main()

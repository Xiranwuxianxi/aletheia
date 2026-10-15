#!/usr/bin/env python3
"""Conservative installer for project/user Claude Code and Codex skill locations."""
from __future__ import annotations
import argparse
import filecmp
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

PROJECT_FILES = {"codex": "AGENTS.md", "claude": "CLAUDE.md"}
GLOBAL_FILES = {"codex": ".codex/AGENTS.md", "claude": ".claude/CLAUDE.md"}
BOOTSTRAP_BEGIN = "<!-- BEGIN ALETHEIA BOOTSTRAP -->"
BOOTSTRAP_END = "<!-- END ALETHEIA BOOTSTRAP -->"


def same_tree(src: Path, dst: Path) -> bool:
    if not dst.is_dir():
        return False
    def included(path: Path, base: Path) -> bool:
        relative = path.relative_to(base)
        return path.is_file() and "__pycache__" not in relative.parts and not path.name.endswith((".pyc", ".pyo"))
    src_files = sorted(p.relative_to(src) for p in src.rglob("*") if included(p, src))
    dst_files = sorted(p.relative_to(dst) for p in dst.rglob("*") if included(p, dst))
    return src_files == dst_files and all(filecmp.cmp(src / rel, dst / rel, shallow=False) for rel in src_files)


def main() -> int:
    p = argparse.ArgumentParser(description="Install Skill Orchestrator safely (opt-in bootstrap)")
    p.add_argument("--platform", choices=("codex", "claude", "both"), default="both")
    p.add_argument("--scope", choices=("project", "user"), default="project")
    p.add_argument("--project", type=Path, default=Path.cwd(), help="project root, default current directory")
    p.add_argument("--bootstrap", action="store_true", help="append an always-on routing hook to AGENTS.md / CLAUDE.md")
    p.add_argument("--mode", choices=("auto", "manual"), default="auto",
                   help="who chooses skills by default: auto (Aletheia decides) or manual (ask the owner by number)")
    p.add_argument("--force", action="store_true", help="back up existing different skill before replacing")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    source = Path(__file__).resolve().parents[1] / "skills" / "aletheia"
    if not (source / "SKILL.md").is_file():
        p.error("bundled skill missing")
    root = args.project.expanduser().resolve() if args.scope == "project" else Path.home()
    platforms = ["codex", "claude"] if args.platform == "both" else [args.platform]
    plan = []
    # Preflight before any writes; refuse overwrites without force.
    for platform in platforms:
        location = ".agents/skills" if platform == "codex" else ".claude/skills"
        target = root / location / "aletheia"
        if target.is_symlink():
            p.error(f"refusing symlink target: {target}")
        different = target.exists() and not same_tree(source, target)
        if different and not args.force:
            p.error(f"different skill already installed at {target}; use --force to back it up and replace")
        bootstrap_path = root / (PROJECT_FILES[platform] if args.scope == "project" else GLOBAL_FILES[platform])
        if args.bootstrap and bootstrap_path.exists() and not bootstrap_path.is_file():
            p.error(f"bootstrap path is not a file: {bootstrap_path}")
        if args.bootstrap and bootstrap_path.is_symlink():
            p.error(f"refusing symlink bootstrap file: {bootstrap_path}")
        plan.append((platform, target, different, bootstrap_path))
    actions = []
    for platform, target, different, instructions in plan:
        if args.dry_run:
            actions.append({"operation": "would_install_or_keep", "target": str(target), "different": different})
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if different:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = target.with_name(target.name + ".backup-" + stamp)
                if backup.exists():
                    p.error(f"backup already exists: {backup}")
                target.rename(backup)
                actions.append({"operation": "backup", "target": str(backup)})
            if not target.exists():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                actions.append({"operation": "installed", "target": str(target)})
            else:
                actions.append({"operation": "unchanged", "target": str(target)})
        if args.bootstrap:
            # The owner picks the operating mode once; the block records it so the
            # preference survives across sessions without re-asking every task.
            mode_line = (
                "Selection mode: **auto** (Aletheia decides and shows its reasoning, including rejected "
                "candidates). The owner may take over at any time by asking to choose skills manually; "
                "that preference persists until they ask to switch back."
                if args.mode == "auto" else
                "Selection mode: **manual** (ask the owner which skills to use, by number, before acting; "
                "they may pick one, several, or none). Switch back to auto whenever they ask."
            )
            hook = (f"{BOOTSTRAP_BEGIN}\n"
                    f"Before each substantive task, check whether an installed Agent Skill materially improves the requested output. "
                    f"When appropriate, activate `{target / 'SKILL.md'}` or the host-native skill entry, "
                    f"read its full instructions, and invoke relevant specialized skills before doing the work. "
                    f"{mode_line} "
                    f"Run `python {target / 'scripts' / 'router.py'} inventory --limit 50` to list every installed "
                    f"skill with numbers when the owner chooses manually, and `--query <term>` to narrow a large list. "
                    f"Use only available tools; do not claim a skill was used without real execution. "
                    f"For simple tasks without a relevant skill, answer directly.\n"
                    f"{BOOTSTRAP_END}\n")
            existing = instructions.read_text(encoding="utf-8") if instructions.is_file() else ""
            if BOOTSTRAP_BEGIN in existing and BOOTSTRAP_END not in existing:
                p.error(f"malformed prior bootstrap block in {instructions}")
            if BOOTSTRAP_BEGIN in existing:
                start = existing.index(BOOTSTRAP_BEGIN)
                end = existing.index(BOOTSTRAP_END, start) + len(BOOTSTRAP_END)
                updated = existing[:start] + hook.rstrip("\n") + existing[end:]
            else:
                updated = existing.rstrip() + ("\n\n" if existing.strip() else "") + hook
            if args.dry_run:
                actions.append({"operation": "would_bootstrap", "path": str(instructions)})
            else:
                instructions.parent.mkdir(parents=True, exist_ok=True)
                if updated != existing:
                    instructions.write_text(updated, encoding="utf-8")
                actions.append({"operation": "bootstrap_upsert", "path": str(instructions)})
    print(json.dumps({"actions": actions, "notice": "Restart or refresh the agent session if your platform requires it. Bootstrap instructions do not grant tool access."}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

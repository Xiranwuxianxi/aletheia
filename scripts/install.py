#!/usr/bin/env python3
"""Install the aletheia skill into any host this project knows about.

The previous version hard-coded two platforms while the registry tracked
fourteen, so the hosts actually in use — Kimi, Gemini, Copilot, Hermes,
OpenClaw, Qwen — had no install path at all.

Design rules, unchanged from the original installer:

* Refuse to overwrite a different installation unless --force, and back it up
  rather than deleting it.
* Refuse a symlinked target. A copy landing through a link can rewrite whatever
  the link points at.
* Bootstrap instructions are an upsert between markers, so re-running is
  idempotent and never duplicates the block.
* Refuse to touch an identity file. SOUL.md, USER.md, IDENTITY.md and MEMORY.md
  describe who the user is; writing routing instructions into them is not what
  this tool is for, and some hosts treat those files as their persona.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOOTSTRAP_BEGIN = "<!-- BEGIN ALETHEIA BOOTSTRAP -->"
BOOTSTRAP_END = "<!-- END ALETHEIA BOOTSTRAP -->"

# Per-host bootstrap instruction file, project-relative and home-relative.
# A host absent from this table still gets its skill directory; it just does not
# get a routing hook, and `install` says so rather than guessing a filename.
# Sources: each project's own documentation, plus what is actually present on a
# machine where these hosts are installed. Where documentation and the machine
# disagreed, the machine won — Kimi's data root is .kimi-code even though the
# skills directory here is .kimi.
PROJECT_INSTRUCTIONS = {
    "claude": "CLAUDE.md",
    "codex": "AGENTS.md",
    "gemini": "GEMINI.md",
    "qwen": "QWEN.md",
    "copilot": ".github/copilot-instructions.md",
    "droid": "AGENTS.md",
    "crush": "AGENTS.md",
    "kimi": "AGENTS.md",
    "kiro": ".kiro/steering/aletheia.md",
    "opencode": "AGENTS.md",
    "hermes": ".hermes.md",
    "aider": "CONVENTIONS.md",
}
GLOBAL_INSTRUCTIONS = {
    "claude": ".claude/CLAUDE.md",
    "codex": ".codex/AGENTS.md",
    "gemini": ".gemini/GEMINI.md",
    "qwen": ".qwen/QWEN.md",
    "copilot": ".copilot/copilot-instructions.md",
    "droid": ".factory/AGENTS.md",
    "crush": ".config/crush/CRUSH.md",
    "kimi": ".kimi-code/AGENTS.md",
    "kiro": ".kiro/steering/aletheia.md",
    "opencode": ".config/opencode/AGENTS.md",
    # Hermes reads SOUL.md for identity. Writing a routing hook into it would
    # overwrite the persona, so its own .hermes.md is used instead.
    "hermes": ".hermes.md",
}
# Never write these, whatever a host claims to read.
PROTECTED_NAMES = {"SOUL.md", "USER.md", "IDENTITY.md", "MEMORY.md"}


def same_tree(src: Path, dst: Path) -> bool:
    if not dst.is_dir():
        return False

    def included(path: Path, base: Path) -> bool:
        relative = path.relative_to(base)
        return (
            path.is_file()
            and "__pycache__" not in relative.parts
            and not path.name.endswith((".pyc", ".pyo"))
        )

    src_files = sorted(p.relative_to(src) for p in src.rglob("*") if included(p, src))
    dst_files = sorted(p.relative_to(dst) for p in dst.rglob("*") if included(p, dst))
    return src_files == dst_files and all(
        filecmp.cmp(src / rel, dst / rel, shallow=False) for rel in src_files
    )


def load_registry() -> dict:
    """Read TELEMETRY_HOSTS out of router.py without importing the world."""
    import importlib.util

    router = Path(__file__).resolve().parents[1] / "skills/aletheia/scripts/router.py"
    spec = importlib.util.spec_from_file_location("aletheia_router", router)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.TELEMETRY_HOSTS


def bootstrap_text(target: Path, mode: str) -> str:
    """The routing hook. Written to be read by a host, not by a person."""
    selection = (
        "Selection mode: **auto** (Aletheia decides and shows its reasoning, including "
        "rejected candidates). The owner may take over at any time by asking to choose "
        "skills manually; that preference persists until they ask to switch back."
        if mode == "auto"
        else "Selection mode: **manual** (ask the owner which skills to use, by number, "
        "before acting; they may pick one, several, or none). Switch back to auto "
        "whenever they ask."
    )
    return (
        f"{BOOTSTRAP_BEGIN}\n"
        "Before each substantive task, check whether an installed Agent Skill materially "
        "improves the requested output. When appropriate, activate "
        f"`{target / 'SKILL.md'}` or the host-native skill entry, read its full "
        "instructions, and invoke relevant specialized skills before doing the work. "
        f"{selection} "
        f"Run `python {target / 'scripts' / 'router.py'} inventory --limit 50` to list "
        "every installed skill with numbers when the owner chooses manually, and "
        "`--query <term>` to narrow a large list. "
        "Use only available tools; do not claim a skill was used without real execution. "
        "For simple tasks without a relevant skill, answer directly.\n"
        f"{BOOTSTRAP_END}\n"
    )


def upsert(path: Path, hook: str) -> str:
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if BOOTSTRAP_BEGIN in existing and BOOTSTRAP_END not in existing:
        raise ValueError(f"malformed prior bootstrap block in {path}")
    if BOOTSTRAP_BEGIN in existing:
        start = existing.index(BOOTSTRAP_BEGIN)
        end = existing.index(BOOTSTRAP_END, start) + len(BOOTSTRAP_END)
        return existing[:start] + hook.rstrip("\n") + existing[end:]
    return existing.rstrip() + ("\n\n" if existing.strip() else "") + hook


def main() -> int:
    p = argparse.ArgumentParser(description="Install the aletheia skill into agent hosts")
    p.add_argument("--host", action="append", default=[], metavar="NAME",
                   help="host key or label, repeatable; default is every installed host")
    p.add_argument("--list", action="store_true", help="list known hosts and exit")
    p.add_argument("--scope", choices=("project", "user"), default="project",
                   help="project = beside the code; user = every project on this machine")
    p.add_argument("--home", type=Path, default=None,
                   help="treat this directory as the user's home instead of the real one; "
                        "for testing the user scope without touching the machine")
    p.add_argument("--project", type=Path, default=Path.cwd(), help="project root")
    p.add_argument("--bootstrap", action="store_true",
                   help="also write an always-on routing hook to the host's instruction file")
    p.add_argument("--mode", choices=("auto", "manual"), default="auto")
    p.add_argument("--force", action="store_true", help="back up a different install before replacing")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    # Every home-relative path goes through this, so a test can point the whole
    # user scope at a temporary directory. Without it, "user" scope in a unit
    # test writes to the developer's actual home directory.
    home = (args.home.expanduser() if args.home else Path.home()).resolve()

    registry = load_registry()
    by_label = {host["label"].lower(): key for key, host in registry.items()}
    by_key = set(registry)

    if args.list:
        print(json.dumps({
            "hosts": [
                {
                    "key": key,
                    "label": host["label"],
                    "skill_dirs": host.get("skills", ()),
                    "project_instructions": PROJECT_INSTRUCTIONS.get(key, "unavailable"),
                    "user_instructions": GLOBAL_INSTRUCTIONS.get(key, "unavailable"),
                }
                for key, host in sorted(registry.items(), key=lambda kv: kv[1]["label"])
            ],
            "note": (
                "'unavailable' means this project does not know a verified instruction "
                "file for the host. The skill directory is still installed; only the "
                "routing hook is skipped, and no filename is guessed."
            ),
        }, ensure_ascii=False, indent=2))
        return 0

    source = Path(__file__).resolve().parents[1] / "skills" / "aletheia"
    if not (source / "SKILL.md").is_file():
        p.error("bundled skill missing")

    selected = []
    for raw in args.host or []:
        key = raw.lower() if raw.lower() in by_key else by_label.get(raw.lower())
        if key is None:
            p.error(f"unknown host {raw!r}; run with --list to see the {len(registry)} known hosts")
        selected.append(key)

    if not selected:
        # Default to hosts whose own directory exists: installing into a host the
        # user does not have would create directories for software that is absent.
        selected = [k for k, h in registry.items()
                    if any((home / s.lstrip("~/")).is_dir() for s in h.get("skills", ()))]

    root = args.project.expanduser().resolve() if args.scope == "project" else home
    instructions_table = PROJECT_INSTRUCTIONS if args.scope == "project" else GLOBAL_INSTRUCTIONS

    plan, skipped = [], []
    seen_targets: dict[str, str] = {}
    seen_bootstraps: dict[str, str] = {}
    # Sort so that hosts able to receive a routing hook claim shared directories
    # first. ~/.agents/skills is listed by six hosts; alphabetical order gives it
    # to Aider, which reads no standard instruction file, and Codex, Gemini, Qwen
    # and the rest would then get the directory but no hook.
    ordered = sorted(
        set(selected),
        key=lambda k: (instructions_table.get(k) is None, registry[k]["label"].lower()),
    )
    for key in ordered:
        host = registry[key]
        # user scope targets the home-relative directory; project scope sits
        # beside the code, in the host's own subdirectory.
        if args.scope == "user":
            bases = [home / s.lstrip("~/") for s in host.get("skills", ())]
            targets = [b / "aletheia" for b in bases]
        else:
            native = host.get("native_skill_dir")
            targets = [root / native / "aletheia"] if native else []

        if not targets:
            skipped.append({"host": host["label"], "reason": "no project-level skill directory known"})
            continue

        rel = instructions_table.get(key)
        if rel is None:
            rel = None

        for target in targets:
            resolved = str(target.resolve())
            # ~/.agents/skills is shared by six hosts, and several hosts list it
            # as a fallback. Installing it once per host would copy the same
            # directory repeatedly, and each host's bootstrap would overwrite
            # the previous one's in the same instruction file.
            if resolved in seen_targets:
                skipped.append({
                    "host": host["label"],
                    "reason": f"already covered via {seen_targets[resolved]} ({target})",
                })
                continue
            # Order matters: ~/.agents/skills is claimed by whichever host sorts
            # first, and alphabetical order hands it to Aider — which has no
            # instruction file, so Codex, Gemini, Qwen and the rest would get the
            # directory but silently lose their bootstrap hook. Prefer a host
            # that can actually be told to use it.
            if resolved in seen_targets and not instructions_table.get(key):
                skipped.append({
                    "host": host["label"],
                    "reason": f"leaves shared directory to {seen_targets[resolved]} ({target})",
                })
                continue
            seen_targets[resolved] = host["label"]

            if target.is_symlink():
                p.error(f"refusing symlink target: {target}")
            if target.name in PROTECTED_NAMES:
                p.error(f"refusing to write a protected identity file: {target}")
            different = target.exists() and not same_tree(source, target)
            if different and not args.force:
                p.error(f"different skill already installed at {target}; use --force to back it up and replace")

            bootstrap_path = None
            if args.bootstrap and rel:
                bootstrap_path = (root if args.scope == "project" else home) / rel
                if bootstrap_path.name in PROTECTED_NAMES:
                    p.error(f"refusing to write a protected identity file: {bootstrap_path}")
                if bootstrap_path.exists() and not bootstrap_path.is_file():
                    p.error(f"bootstrap path is not a file: {bootstrap_path}")
                if bootstrap_path.is_symlink():
                    p.error(f"refusing symlink bootstrap file: {bootstrap_path}")
                key_path = str(bootstrap_path.resolve())
                # Two hosts may name the same instruction file (AGENTS.md). The
                # hook text differs only in the installed path, which is
                # identical, so one write is correct — but say so rather than
                # silently writing twice.
                if key_path in seen_bootstraps:
                    actions_extra = {
                        "operation": "bootstrap_shared",
                        "host": host["label"],
                        "path": str(bootstrap_path),
                        "note": f"same instruction file as {seen_bootstraps[key_path]}; written once",
                    }
                    skipped.append({"host": host["label"],
                                    "reason": f"shares {bootstrap_path} with {seen_bootstraps[key_path]}"})
                    plan.append({"key": key, "label": host["label"], "target": None,
                                 "different": False, "bootstrap": None,
                                 "pre_action": actions_extra})
                    continue
                seen_bootstraps[key_path] = host["label"]
            plan.append({"key": key, "label": host["label"], "target": target,
                         "different": different, "bootstrap": bootstrap_path})

    actions = []
    import shutil

    for item in plan:
        # A host whose instruction file was already written by an earlier host:
        # record that and move on. The skill directory is still its own.
        if item.get("pre_action"):
            actions.append(item["pre_action"])
            continue
        target = item["target"]
        if args.dry_run:
            actions.append({"operation": "would_install_or_keep", "host": item["label"],
                            "target": str(target), "different": item["different"]})
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            if item["different"]:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = target.with_name(target.name + ".backup-" + stamp)
                if backup.exists():
                    p.error(f"backup already exists: {backup}")
                target.rename(backup)
                actions.append({"operation": "backup", "target": str(backup)})
            if not target.exists():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                actions.append({"operation": "installed", "host": item["label"], "target": str(target)})
            else:
                actions.append({"operation": "unchanged", "host": item["label"], "target": str(target)})

        path = item["bootstrap"]
        if args.bootstrap:
            if path is None:
                actions.append({"operation": "bootstrap_skipped", "host": item["label"],
                                "reason": "no verified instruction file for this host; "
                                          "the skill is installed but nothing was written"})
                continue
            hook = bootstrap_text(target, args.mode)
            try:
                updated = upsert(path, hook)
            except ValueError as e:
                p.error(str(e))
            if args.dry_run:
                actions.append({"operation": "would_bootstrap", "host": item["label"], "path": str(path)})
            elif updated != (path.read_text(encoding="utf-8") if path.is_file() else ""):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(updated, encoding="utf-8")
                actions.append({"operation": "bootstrap_upsert", "host": item["label"], "path": str(path)})
            else:
                actions.append({"operation": "bootstrap_unchanged", "host": item["label"], "path": str(path)})

    for entry in skipped:
        actions.append({"operation": "skipped", "host": entry["host"], "reason": entry["reason"]})

    print(json.dumps({
        "actions": actions,
        "hosts_selected": sorted({i["label"] for i in plan}),
        "notice": (
            "Restart or refresh the agent session if your platform requires it. "
            "Bootstrap instructions do not grant tool access. Identity files "
            "(SOUL.md, USER.md, IDENTITY.md, MEMORY.md) are never written."
        ),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
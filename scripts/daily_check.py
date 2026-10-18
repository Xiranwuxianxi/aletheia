#!/usr/bin/env python3
"""Daily library health check.

Runs the audit plus a telemetry sample once a day and writes a rotating log
under the local Aletheia directory. Nothing leaves this machine.

Read-only by default: it reports what needs attention and what can be repaired,
but only rewrites files when `--fix` is passed. It never deletes a skill.

Cross-platform: no shell needed, so the same command works under Task Scheduler,
cron, launchd or a terminal.

Examples
--------
    python scripts/daily_check.py                  # report only
    python scripts/daily_check.py --fix            # also apply safe repairs
    python scripts/daily_check.py --notify         # print a ready-to-paste summary
    python scripts/daily_check.py --quiet          # only report when something needs attention
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ROUTER = REPO / "skills" / "aletheia" / "scripts" / "router.py"

# Conventional skill roots, matching what the router scans by default.
DEFAULT_ROOTS = [
    Path.home() / ".workbuddy" / "skills",
    Path.home() / ".workbuddy" / "plugins" / "cache",
    Path.home() / ".claude" / "skills",
    Path.home() / ".agents" / "skills",
]

LOG_DIR = Path.home() / ".aletheia"
LOG_FILE = LOG_DIR / "daily-check.log"
KEEP_LOG_LINES = 400


def run_router(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-B", str(ROUTER), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout or proc.stderr


def existing_roots(extra: list[str]) -> list[str]:
    roots = [str(r) for r in DEFAULT_ROOTS if r.is_dir()]
    roots += [r for r in extra if Path(r).expanduser().is_dir()]
    return roots


def append_log(lines: list[str]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"\n===== {stamp} =====\n")
        handle.write("\n".join(lines) + "\n")
    # Rotate by trimming in place; the log is a convenience, not an archive.
    kept = LOG_FILE.read_text(encoding="utf-8").splitlines()[-KEEP_LOG_LINES:]
    LOG_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8")


def build_summary(audit: dict, telemetry: dict, active: dict | None = None,
                  update: dict | None = None, versions: dict | None = None) -> str:
    counts = audit["counts"]
    hosts = telemetry.get("hosts", {})
    readable = [h for h, v in hosts.items() if v.get("available")]
    total = sum(
        v.get("billable_tokens_excluding_cache_read", 0) or 0 for v in hosts.values() if v.get("available")
    )

    lines = [
        f"Aletheia daily check · {datetime.now().strftime('%Y-%m-%d')}",
        "",
        f"Library: {audit['scanned']} scanned · {counts['ok']} healthy · {counts['broken']} broken "
        f"({counts['blocking']} need a human) · {counts['stale']} stale · {counts['duplicate']} duplicated",
    ]
    if audit["recommendations"]:
        lines.append("")
        lines.append("Needs attention:")
        for rec in audit["recommendations"]:
            lines.append(f"  · {rec['action']}: {rec['target']}")
            lines.append(f"      {rec['command']}")
    else:
        lines.append("Library needs no attention.")

    lines.append("")
    if readable:
        lines.append(
            f"Token usage read from {', '.join(hosts[h]['label'] for h in readable)}: "
            f"{total:,} billable tokens (input + output + cache write; cache read excluded)"
        )
    missing = [v["label"] for v in hosts.values() if not v.get("available")]
    if missing:
        lines.append(f"No token telemetry: {', '.join(missing)} — read from that host's own UI.")
    lines.append("These totals cover the scanned session files only, not all historical usage.")

    if update is not None:
        lines.append("")
        lines.append("Update check:")
        if not update.get("checked"):
            lines.append(f"  not checked: {update.get('reason', 'unknown')}")
        elif update.get("update_available") is True:
            lines.append(
                f"  UPDATE AVAILABLE: {update.get('local_tag') or update.get('local_version')}"
                f" -> {update.get('latest_tag')}"
            )
            if isinstance(update.get("commits_behind"), int):
                lines.append(f"  {update['commits_behind']} commit(s) behind")
            for line in (update.get("commits_preview") or [])[:5]:
                lines.append(f"    {line}")
        elif update.get("update_available") is False:
            lines.append(f"  up to date: {update.get('latest_tag')} ({update.get('local_version')})")
        else:
            lines.append(f"  unknown: {update.get('reason', 'no reason given')}")
        lines.append("  Aletheia detects updates but never applies them — that stays your call.")

    if versions is not None:
        summary_block = versions.get("source_breakdown", {})
        lines.append("")
        lines.append("Skill versions:")
        lines.append(
            f"  {versions.get('total_unique_skills')} skills ·"
            f" {versions.get('checkable_against_upstream', 0)} comparable to an upstream ·"
            f" {versions.get('declared_version_only', 0)} version-declared only ·"
            f" {versions.get('no_version_signal', 0)} with no version signal"
        )
        for kind, count in sorted(summary_block.items(), key=lambda x: -x[1]):
            lines.append(f"    {kind}: {count}")
        outdated = versions.get("outdated") or []
        if outdated:
            lines.append(f"  OUTDATED ({len(outdated)}):")
            for item in outdated[:10]:
                lines.append(
                    f"    {item['name']}: {item.get('local')} -> {item.get('remote')}"
                )
                if item.get("upstream"):
                    lines.append(f"      {item['upstream']}")
        else:
            lines.append("  no outdated skills")
        edited = versions.get("locally_modified_since_install") or []
        if edited:
            lines.append(
                f"  {len(edited)} skill(s) edited since install — an update would overwrite local changes"
            )
            for item in edited[:3]:
                lines.append(f"    {item['name']} (installed {item.get('installed_version')})")

    if active:
        totals = active["token_totals"]
        context = active["context_load"]
        inv = active["inventory"]
        lines.append("")
        lines.append("Active measurement (read from disk, no host asked):")
        lines.append(
            f"  tokens: {totals['input']:,} in · {totals['output']:,} out ·"
            f" {totals['cache_read']:,} cache read"
        )
        lines.append(f"  completeness: {totals['completeness']}")
        lines.append(
            f"  library: {inv['unique_skills']} unique skills"
            f" ({inv['duplicate_installs']} duplicate installs)"
        )
        lines.append(
            f"  context cost: {context['metadata_tokens_est']:,} est. tokens of metadata"
            f" for {context['visible_skills']} visible skill(s)"
        )
        blocked = active.get("unmeasurable_here", {})
        unavailable = [k for k, v in blocked.items() if v == "unavailable"]
        if unavailable:
            lines.append(f"  not measurable here: {', '.join(unavailable)}")

    if audit["fix_applied"]:
        fixed = [b for b in audit["broken"] if b.get("repaired")]
        if fixed:
            lines.append("")
            lines.append(f"Repaired {len(fixed)} skill(s): " + ", ".join(b["name"] for b in fixed[:8]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily skill-library health check")
    parser.add_argument("--fix", action="store_true", help="apply safe repairs (frontmatter only; never deletes)")
    parser.add_argument("--root", action="append", default=[], help="extra skill root (repeatable)")
    parser.add_argument("--notify", action="store_true", help="print a copy-pasteable summary")
    parser.add_argument("--quiet", action="store_true", help="print only when something needs attention")
    parser.add_argument("--since-days", type=float, default=90.0, help="staleness threshold")
    parser.add_argument("--json", action="store_true", help="emit the raw audit JSON")
    args = parser.parse_args()

    if not ROUTER.is_file():
        print(f"router.py not found at {ROUTER}", file=sys.stderr)
        return 2

    roots = existing_roots(args.root)
    if not roots:
        print("No skill roots found; nothing to audit.", file=sys.stderr)
        return 0

    audit_args = ["audit", "--unused-days", str(args.since_days), "--json"]
    for root in roots:
        audit_args += ["--root", root]
    if args.fix:
        audit_args.append("--fix")

    code, out = run_router(*audit_args)
    try:
        audit = json.loads(out)
    except ValueError:
        print(f"Audit produced unparseable output:\n{out[:500]}", file=sys.stderr)
        return 2

    # `estimate` is the active walk: it measures what it can from local files
    # without depending on any host volunteering its numbers.
    _, act_out = run_router("estimate", "--since-days", "30")
    try:
        active = json.loads(act_out)
    except ValueError:
        active = None

    # `update` compares this checkout against its remote. Detection only: it
    # never fetches into the working tree or rewrites a file.
    _, upd_out = run_router("update")
    try:
        update = json.loads(upd_out)
    except ValueError:
        update = {"checked": False, "reason": "update check produced no readable output"}

    # Version state across the whole library. Outdated skills make the exit
    # code non-zero so the scheduler surfaces them.
    _, ver_out = run_router("versions")
    try:
        versions = json.loads(ver_out)
    except ValueError:
        versions = None

    _, tel_out = run_router("telemetry", "--since-days", "30")
    try:
        telemetry = json.loads(tel_out)
    except ValueError:
        telemetry = {"hosts": {}}

    summary = build_summary(audit, telemetry, active, update, versions)
    append_log([summary, "", f"audit exit code: {code}"])

    outdated_count = len((versions or {}).get("outdated") or [])
    needs_attention = (
        bool(audit["recommendations"])
        or update.get("update_available") is True
        or outdated_count > 0
    )
    if args.json:
        print(json.dumps(
            {"audit": audit, "telemetry": telemetry, "active_measurement": active,
             "update": update, "versions": versions},
            ensure_ascii=False, indent=2,
        ))
    elif args.quiet and not needs_attention:
        pass
    elif args.notify or args.quiet or not needs_attention:
        print(summary)
    else:
        print(summary)

    # Exit 1 only for problems a script cannot fix, so schedulers can alert.
    return 1 if audit["counts"]["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main())

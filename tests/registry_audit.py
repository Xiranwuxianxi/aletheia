"""Report each host's registered skill directory against this machine.

Read-only. A registry entry pointing at a directory the host does not use is
worse than a missing entry: the library looks complete while those skills stay
invisible. Gemini was found this way — registered as ~/.gemini/extensions,
which does not exist, while the host actually reads ~/.gemini/skills.

A directory that is absent is not automatically wrong: the host may simply not
be installed. So this reports, and only flags the case that matters — a host
that has a differently-named directory holding skills.

Not part of the unit suite: the answer depends on what is installed, so it is a
diagnostic to run by hand rather than an assertion that cannot hold everywhere.
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rt", ROOT / "skills/aletheia/scripts/router.py")
router = importlib.util.module_from_spec(spec)
sys.modules["rt"] = router
spec.loader.exec_module(router)

home = pathlib.Path.home()


def count_dirs(path: pathlib.Path) -> int:
    try:
        return len([p for p in path.iterdir() if p.is_dir()])
    except OSError:
        return 0


live, absent = [], []
for key, host in sorted(router.TELEMETRY_HOSTS.items(), key=lambda kv: kv[1]["label"]):
    for raw in host.get("skills", ()):
        path = home / raw.lstrip("~/")
        if path.is_dir() and count_dirs(path):
            live.append((host["label"], raw, count_dirs(path)))
        else:
            absent.append((host["label"], raw))

print(f"{'HOST':<22}{'DIRECTORY':<38}{'ENTRIES':>8}")
print("-" * 68)
for label, raw, n in live:
    print(f"{label:<22}{raw:<38}{n:>8}")
print(f"\n{len(live)} directories in use, {len(absent)} registered but absent here")

if not absent:
    sys.exit(0)

# For each absent directory, look for a sibling under the same parent whose
# name differs — that is the signature of a mis-registration rather than an
# uninstalled host.
print("\nabsent, and whether a sibling spelling looks like the real one:")
suspect = 0
for label, raw in absent:
    declared = home / raw.lstrip("~/")
    parent = declared.parent
    if not parent.is_dir():
        print(f"  {label:<22}{raw:<38}parent absent — host probably not installed")
        continue
    # Same parent, different leaf name (gemini/skills vs gemini/extensions).
    alternatives = [
        p for p in parent.iterdir()
        if p.is_dir() and p.name != declared.name and count_dirs(p)
        and (p / "SKILL.md").exists() is False
    ]
    skill_dirs = [p for p in parent.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()]
    if skill_dirs:
        names = ", ".join(f"{p.name}/ ({count_dirs(p)})" for p in skill_dirs)
        print(f"  {label:<22}{raw:<38}SUSPECT — parent holds {names}")
        suspect += 1
    elif alternatives:
        names = ", ".join(p.name for p in alternatives)
        print(f"  {label:<22}{raw:<38}siblings present: {names}")
    else:
        print(f"  {label:<22}{raw:<38}nothing else here — host likely not installed")

sys.exit(1 if suspect else 0)
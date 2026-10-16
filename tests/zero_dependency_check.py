"""Reproduce the CI failure under a genuinely PyYAML-free environment.

The GitHub Actions runner installs no third-party packages, so `import yaml`
fails there. Locally PyYAML IS present, which is why this only reproduces on
Linux. Both paths must agree, or a skill passes on a dev machine and fails CI.
"""
import builtins
import importlib.util
import pathlib
import sys
import tempfile

REAL_IMPORT = builtins.__import__


def block_yaml(name, *args, **kwargs):
    if name == "yaml" or name.startswith("yaml."):
        raise ImportError("yaml blocked for this test")
    return REAL_IMPORT(name, *args, **kwargs)


spec = importlib.util.spec_from_file_location(
    "rt", pathlib.Path(__file__).resolve().parents[1] / "skills/aletheia/scripts/router.py"
)
router = importlib.util.module_from_spec(spec)
sys.modules["rt"] = router
builtins.__import__ = block_yaml
try:
    spec.loader.exec_module(router)
finally:
    builtins.__import__ = REAL_IMPORT

CRLF = chr(13) + chr(10)
NL = chr(10)
base = pathlib.Path(tempfile.mkdtemp())
failures = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}: {got!r}" + ("" if ok else f"  (expected {want!r})"))
    if not ok:
        failures.append(label)


# 1. allowed-tools as a block list must be recognised, not called malformed.
d = base / "listtools"
d.mkdir()
(d / "SKILL.md").write_text(
    NL.join(["---", "name: listtools", "description: Uses a list.",
             "allowed-tools:", "  - Bash(git:*)", "  - Read", "---", "", "# body", ""]),
    encoding="utf-8",
)
check("diagnose allowed-tools list", router.diagnose_skill(d / "SKILL.md")["kind"], "allowed_tools_list")
changed, note = router.repair_skill(d / "SKILL.md", "allowed_tools_list")
check("repair returns changed", changed, True)
check("repair result is ok", router.diagnose_skill(d / "SKILL.md")["kind"], "ok")
check("allowed-tools flattened", "allowed-tools: Bash(git:*) Read" in (d / "SKILL.md").read_text(encoding="utf-8"), True)
check("body survived", "# body" in (d / "SKILL.md").read_text(encoding="utf-8"), True)

# 2. CRLF variant must behave identically.
d2 = base / "crlf"
d2.mkdir()
with open(d2 / "SKILL.md", "w", encoding="utf-8", newline="") as h:
    h.write(CRLF.join(["---", "name: crlf", "description: Uses a list.",
                       "allowed-tools:", "  - Bash(git:*)", "  - Read", "---", "", "# body", ""]))
check("CRLF diagnose", router.diagnose_skill(d2 / "SKILL.md")["kind"], "allowed_tools_list")
router.repair_skill(d2 / "SKILL.md", "allowed_tools_list")
check("CRLF repair ok", router.diagnose_skill(d2 / "SKILL.md")["kind"], "ok")

# 3. Over-long description must be detected and actually shortened.
d3 = base / "toolong"
d3.mkdir()
(d3 / "SKILL.md").write_text(
    NL.join(["---", "name: toolong", "description: " + "x" * 1200, "---", "", "# keep", ""]),
    encoding="utf-8",
)
before = len((d3 / "SKILL.md").read_text(encoding="utf-8"))
check("describe long", router.diagnose_skill(d3 / "SKILL.md")["kind"], "description_too_long")
router.repair_skill(d3 / "SKILL.md", "description_too_long")
after = len((d3 / "SKILL.md").read_text(encoding="utf-8"))
check("file got shorter", after < before, True)
check("body survived truncation", "# keep" in (d3 / "SKILL.md").read_text(encoding="utf-8"), True)

# 4. A folded description over the limit must also be caught.
d4 = base / "folded"
d4.mkdir()
(d4 / "SKILL.md").write_text(
    NL.join(["---", "name: folded", "description: >", "  " + "y" * 1300, "---", "", "# body", ""]),
    encoding="utf-8",
)
check("folded long", router.diagnose_skill(d4 / "SKILL.md")["kind"], "description_too_long")

# 5. Discovery works without PyYAML. Fixtures are built last, in a clean
#    directory, so this asserts on pristine files rather than ones steps 1-4
#    already repaired — otherwise the result depends on execution order.
fresh = base / "fresh"
fresh.mkdir()


def write(dirname: str, lines: list[str], newline: str = NL) -> None:
    directory = fresh / dirname
    directory.mkdir()
    with open(directory / "SKILL.md", "w", encoding="utf-8", newline="") as handle:
        handle.write(newline.join(lines))


write("healthy", ["---", "name: healthy", "description: A fine skill.", "---", "", "# body", ""])
write("listtools", ["---", "name: listtools", "description: Uses a list.",
                    "allowed-tools:", "  - Bash(git:*)", "  - Read", "---", "", "# body", ""])
write("toolong", ["---", "name: toolong", "description: " + "x" * 1200, "---", "", "# body", ""])
write("folded", ["---", "name: folded", "description: >", "  " + "y" * 1300, "---", "", "# body", ""])

skills, issues = router.discover([fresh])
# `toolong` and `folded` are over-long at load time: a hard failure by design,
# which is what `audit --fix` exists to repair first. Both paths must agree.
check(
    "discovered healthy skills",
    sorted(s.name for s in skills),
    ["healthy", "listtools"],
)
check(
    "over-long descriptions rejected at load",
    sum(1 for i in issues if "1024" in i["error"]),
    2,
)
check(
    "list flagged as a warning, not an error",
    sorted({i.get("severity", "error") for i in issues if "allowed-tools" in i["error"]}),
    ["warning"],
)

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("zero-dependency path agrees with the PyYAML path")

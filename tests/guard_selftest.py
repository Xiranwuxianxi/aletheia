"""Verify each check of the canonical-path guard actually fires.

Copies in bash went through CRLF translation on Windows, which both corrupted
the file and raced with the test run. Doing the patch in Python keeps bytes
exact and the steps sequential.
"""
import io
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTER = ROOT / "skills/aletheia/scripts/router.py"
TESTS = ROOT / "tests/test_router.py"
TARGET = "tests.test_router.RouterTests.test_reported_paths_are_canonical_and_consistent"

original = {p: p.read_bytes() for p in (ROUTER, TESTS)}


def run() -> tuple[bool, str]:
    out = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", TARGET],
        capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8",
    )
    detail = ""
    for line in (out.stderr or "").splitlines():
        if "AssertionError" in line:
            detail = line.strip()[:150]
            break
    return out.returncode == 0, detail


def restore() -> None:
    for path, data in original.items():
        path.write_bytes(data)


def probe(label: str, target: pathlib.Path, old: str, new: str) -> None:
    restore()
    text = target.read_text(encoding="utf-8")
    if old not in text:
        print(f"  {label:<44} SKIPPED (anchor not found — probe is broken, not the guard)")
        return
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    passed, detail = run()
    mark = "MISSED" if passed else "fired "
    print(f"  {mark} {label}")
    if detail:
        print(f"           {detail}")


NL = chr(10)
try:
    print("guard on the untouched tree:")
    ok, _ = run()
    print(f"  {'PASS ' if ok else 'FAIL '} baseline")

    print("\nprobe 1 — remove the explicit branch's resolve():")
    probe(
        "load_session_manifest explicit branch",
        ROUTER,
        "        path = path.resolve()" + NL + "        try:",
        "        try:",
    )

    print("\nprobe 2 — an assertion that resolves both sides:")
    probe(
        "assertEqual(a.resolve(), b.resolve())",
        TESTS,
        "    def test_active_measurement_needs_no_host(self):",
        "    def test_probe_both_sides(self):" + NL
        + "        a = Path('x')" + NL
        + "        b = Path('y')" + NL
        + "        self.assertEqual(a.resolve(), b.resolve())" + NL + NL
        + "    def test_active_measurement_needs_no_host(self):",
    )

    print("\nprobe 3 — a duplicated test definition:")
    probe(
        "two tests with one name",
        TESTS,
        "    def test_active_measurement_needs_no_host(self):",
        "    def test_zz_dup(self):" + NL + "        pass" + NL + NL
        + "    def test_zz_dup(self):" + NL + "        pass" + NL + NL
        + "    def test_active_measurement_needs_no_host(self):",
    )
finally:
    restore()

print("\nafter restore:")
ok, _ = run()
print(f"  {'PASS' if ok else 'FAIL'}  guard passes on the real tree")

#!/usr/bin/env python3
"""Host hook entry point: hard-guarantee aletheia routing, owner-controlled.

Wired into a host's hook runtime (e.g. WorkBuddy ``~/.workbuddy/settings.json``
``hooks.SessionStart`` and ``hooks.UserPromptSubmit``), this runs mechanically
— before the model can decide anything — and injects routing context into the
conversation. Unlike an instruction file, which the model may ignore, the
injection itself is guaranteed; this script is what turns "should route" into
"does route".

But it is never hardwired against the owner. Every configuration level can
switch it off or narrow which events inject (see ``router.hook_settings``):

* ``aletheia-session.json`` near the cwd — per-session mute: ``{"hook": "off"}``
* ``aletheia-config.json`` near the cwd — per-project: ``{"hook": "off"}``
* ``~/.aletheia/config.json`` — machine-wide owner switch
* ``router.py hook --set off|on`` flips the machine switch instantly; the host's
  settings file is never touched, so no re-approval is needed to silence this.

When disabled, or when the event is not in the owner's event list, the script
prints nothing and exits 0: a true no-op, not a nag.

Events (from the payload's ``hook_event_name``, or ``--event`` for hosts that
wire commands per event):

* ``SessionStart``   → first turn of a conversation: bootstrap the routing
  protocol so the very first task already goes through the preflight.
* ``UserPromptSubmit`` → every prompt: run retrieval over the installed skill
  library and inject the advisory candidates for THIS prompt.

Output is the documented JSON envelope (``hookSpecificOutput.additionalContext``)
so hosts inject precisely; the exit code is always 0 — a hook must never block
the owner's message. Degradation is honest: if retrieval fails, the output says
so and falls back to the protocol reminder instead of inventing candidates.

Privacy: the prompt text is read from stdin, used in-process for retrieval, and
never echoed into the injected context or the process list.

Performance: a full library scan costs seconds on a large machine and this hook
runs on every prompt, so discovered skills are cached in ``~/.aletheia/`` while
the root set is unchanged and the cache is younger than ALETHEIA_HOOK_TTL
seconds (default 600). The snapshot age is printed so a stale list is never
presented as live.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

CACHE_DIR_NAME = ".aletheia"
CACHE_NAME = "hook-cache.json"
DEFAULT_TTL_SECONDS = 600
TOP_CANDIDATES = 3

EVENT_ALIASES = {
    "sessionstart": "session-start",
    "session-start": "session-start",
    "userpromptsubmit": "prompt-submit",
    "user-prompt-submit": "prompt-submit",
    "prompt-submit": "prompt-submit",
}
EVENT_OUTPUT_NAMES = {"session-start": "SessionStart", "prompt-submit": "UserPromptSubmit"}

PROTOCOL_AUTO = (
    "Selection mode: auto — choose the skill(s) yourself and disclose the decision, "
    "including rejected candidates and why."
)
PROTOCOL_MANUAL = (
    "Selection mode: manual — present the candidates as a numbered list and wait for "
    "the owner to pick; do not act until they answer."
)
PROTOCOL_DISCLOSURE = (
    "For non-trivial tasks disclose five stages: Intent, Candidates (including "
    "rejected ones and why), Decision, Operations, Verdict."
)
PROTOCOL_HONESTY = (
    "Read a candidate's full SKILL.md before claiming or using it; never claim a "
    "skill was used without real execution. If no candidate fits, answer directly."
)


def load_router():
    """Import the router that ships beside this script (repo or installed copy)."""
    router = Path(__file__).resolve().parent / "router.py"
    spec = importlib.util.spec_from_file_location("aletheia_router_hook", router)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {router}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cache_path() -> Path:
    override = os.getenv("ALETHEIA_HOOK_CACHE")
    if override:
        return Path(override).expanduser()
    return Path.home() / CACHE_DIR_NAME / CACHE_NAME


def cache_ttl() -> float:
    try:
        return float(os.getenv("ALETHEIA_HOOK_TTL", DEFAULT_TTL_SECONDS))
    except ValueError:
        return DEFAULT_TTL_SECONDS


def load_cache(path: Path, roots: list[str]) -> list[dict] | None:
    """Return cached skills when the snapshot covers exactly these roots and is fresh."""
    try:
        if time.time() - path.stat().st_mtime > cache_ttl():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("roots") != roots:
        return None
    skills = data.get("skills")
    return skills if isinstance(skills, list) else None


def save_cache(path: Path, roots: list[str], skills: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"created": time.time(), "roots": roots, "skills": skills},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass  # a read-only machine simply rescans next time


def resolve_event(payload: dict, override: str | None) -> str | None:
    """Map the host's event name onto ours; None means 'do not inject'."""
    raw = override or str(payload.get("hook_event_name") or "")
    key = EVENT_ALIASES.get(raw.strip().lower())
    if key:
        return key
    if override is None and not raw:
        # A host that labels nothing: a prompt field is unambiguous evidence of
        # a prompt-submit. Its absence proves nothing, so stay silent instead
        # of guessing.
        return "prompt-submit" if payload.get("prompt") is not None else None
    return None


def protocol_lines(mode: str, skill_dir: Path) -> list[str]:
    return [
        PROTOCOL_MANUAL if mode == "manual" else PROTOCOL_AUTO,
        PROTOCOL_DISCLOSURE,
        PROTOCOL_HONESTY,
        f"Full protocol: {skill_dir / 'SKILL.md'}",
    ]


def bootstrap_context(cwd: Path, router, skill_dir: Path) -> str:
    """SessionStart: prime the routing preflight for this conversation."""
    mode = router.load_mode_config(cwd / "aletheia-config.json").get("mode", "auto")
    lines = [
        "[aletheia] skill routing is ready for this conversation (injected at session start).",
        *protocol_lines(mode, skill_dir),
        "For the first task, run the preflight before working: list candidates with "
        f"`python {skill_dir / 'scripts' / 'router.py'} route \"<task>\" --top 5` (or "
        "inventory --query <term>), then activate the chosen skill as described above.",
    ]
    return "\n".join(lines)


def prompt_context(prompt: str, cwd: Path, router, skill_dir: Path) -> str:
    """UserPromptSubmit: retrieval candidates for THIS prompt plus the protocol."""
    mode = router.load_mode_config(cwd / "aletheia-config.json").get("mode", "auto")
    header = "[aletheia] skill routing is active for this prompt (hard-injected by hook)."
    if not prompt.strip():
        return "\n".join([header, *protocol_lines(mode, skill_dir)])

    roots = [str(Path(r)) for r in router.default_roots(Path(cwd))]
    cache = cache_path()
    skills = load_cache(cache, roots)
    snapshot = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cache.stat().st_mtime))
                if skills is not None and cache.is_file() else None)
    if skills is None:
        skills = [router.asdict(s) for s in router.discover([Path(r) for r in roots])[0]]
        save_cache(cache, roots, skills)
        snapshot = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    result = router.route(prompt, [router.Skill(**s) for s in skills],
                          top=TOP_CANDIDATES, threshold=router.DEFAULT_THRESHOLD)
    lines = [header,
             f"Skill library snapshot: {snapshot} ({len(skills)} skills scanned).",
             *protocol_lines(mode, skill_dir)]
    candidates = result.get("candidates") or []
    if candidates:
        lines.append("Advisory candidates for this prompt (metadata retrieval only):")
        for i, c in enumerate(candidates, 1):
            lines.append(f" {i}. {c['name']} (score {c['score']}) — {c['path']}")
    else:
        lines.append("No candidate reached the threshold for this prompt.")
    return "\n".join(lines)


def envelope(event: str, text: str) -> str:
    """The documented hook output shape: precise context injection, never blocking."""
    return json.dumps({
        "continue": True,
        "suppressOutput": False,
        "hookSpecificOutput": {
            "hookEventName": EVENT_OUTPUT_NAMES.get(event, event),
            "additionalContext": text,
        },
    }, ensure_ascii=False)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):  # Python < 3.7 or closed stream
        pass
    argv = sys.argv[1:]
    override = None
    if "--event" in argv and argv.index("--event") + 1 < len(argv):
        override = argv[argv.index("--event") + 1]

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except (OSError, ValueError):
        payload = {}
    prompt = str(payload.get("prompt") or "")
    cwd_value = (payload.get("cwd") or os.getenv("CODEBUDDY_PROJECT_DIR")
                 or os.getenv("CLAUDE_PROJECT_DIR") or Path.cwd())
    cwd = Path(str(cwd_value))

    event = resolve_event(payload, override)
    try:
        router = load_router()
        settings = router.hook_settings(cwd=cwd)
        if not settings["enabled"] or event is None or event not in settings["events"]:
            # The owner said no, or this event is not theirs to inject into.
            # Silence is the feature: exit 0 and add nothing to the conversation.
            return 0
        skill_dir = Path(__file__).resolve().parent.parent
        if event == "session-start":
            text = bootstrap_context(cwd, router, skill_dir)
        else:
            text = prompt_context(prompt, cwd, router, skill_dir)
    except Exception as exc:  # noqa: BLE001 — a hook must never block a prompt
        event = event or "prompt-submit"
        text = (
            "[aletheia] skill routing is active (hard-injected by hook), but candidate "
            f"retrieval is unavailable ({type(exc).__name__}). "
            + PROTOCOL_DISCLOSURE + " " + PROTOCOL_HONESTY
        )
    print(envelope(event, text))
    return 0


if __name__ == "__main__":
    sys.exit(main())

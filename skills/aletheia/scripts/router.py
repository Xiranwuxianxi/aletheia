#!/usr/bin/env python3
"""Local, read-only Agent Skills metadata discovery and candidate retrieval.

Stdlib-only. Never executes discovered skills or sends task text to a service.
The model/runtime remains responsible for semantic selection and actual invocation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

VERSION = "1.4.0"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WORD_RE = re.compile(r"[a-z][a-z0-9+-]{1,}|[\u3400-\u9fff]{2,}", re.I)
# Shared defaults. The CLI and the offline `eval` command must agree, otherwise
# the reported pass rate would not describe the behavior users actually get.
DEFAULT_TOP = 5
DEFAULT_THRESHOLD = 16
EVAL_TOP = 3
# This skill must never recommend itself as a candidate for another task.
SELF_NAME = "aletheia"
STOPWORDS = {"when", "with", "that", "from", "this", "and", "the", "for", "use", "using", "skill", "skills", "file", "files", "task", "tasks", "into", "your", "can", "will", "what", "please", "which", "help", "需要", "帮我", "一个", "如何", "使用", "进行", "这个", "生成", "制作", "创建"}
# Retrieval hints only; not a complete ontology or evidence of actual invocation.
DOMAIN_ALIASES = {
    "pdf": ["pdf", ".pdf", "pdf文件", "pdf文档", "pdf处理", "扫描版", "pdf-processing"],
    "spreadsheet": ["xlsx", "xls", "excel", "csv", "spreadsheet", "电子表格", "数据表格", "工作簿", "spreadsheet-analysis"],
    "slides": ["pptx", "ppt", "powerpoint", "slides", "presentation", "幻灯片", "演示文稿", "汇报演示"],
    "word": ["docx", "word", "文档排版", "文字文档", "合同文档", "word-processing"],
    "research": ["research", "web search", "web-research", "browse", "internet", "在线检索", "搜集资料", "网页搜索", "网络调研", "查资料", "找资料"],
    "code": ["code review", "github", "pull request", "repository", "代码审查", "代码仓库", "git", "issue", "开源项目"],
    "data": ["analytics", "data analysis", "dashboard", "business intelligence", "数据分析", "数据可视化", "仪表盘", "指标分析", "kpi", "看板"],
    "design": ["product design", "prototype", "ux", "ui design", "产品设计", "原型设计", "交互设计", "界面设计"],
    "image": ["image", "images", "poster", "cover art", "图片", "封面", "插画", "海报", "配图"],
    "video": ["video", "editing", "subtitle", "剪辑", "视频", "字幕", "口播"],
    "testing": ["unit test", "pytest", "regression", "测试用例", "单元测试", "自动化测试", "回归测试"],
}


class SkillError(ValueError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: str
    root: str


def _frontmatter(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise SkillError("SKILL.md symlinks are not read")
    try:
        if path.stat().st_size > 131_072:
            raise SkillError("SKILL.md exceeds 128 KiB metadata scan limit")
        data = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as e:
        raise SkillError(f"cannot read: {e}") from e
    lines = data.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError("missing opening YAML frontmatter fence")
    end = next((i for i, line in enumerate(lines[1:101], start=1) if line.strip() == "---"), -1)
    if end < 0:
        raise SkillError("missing closing frontmatter fence within first 100 lines")
    raw = "\n".join(lines[1:end])
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        yaml = None
    if yaml is not None:
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise SkillError(f"invalid YAML: {e}") from e
        if not isinstance(parsed, dict):
            raise SkillError("YAML frontmatter must be a mapping")
        return parsed
    # Zero-dependency fallback for common scalar frontmatter and folded/literal descriptions.
    # Install PyYAML for general YAML features such as anchors and multiline quoting.
    result: dict[str, str] = {}
    i = 0
    lines = raw.splitlines()
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#") or line[0].isspace():
            i += 1
            continue
        if ":" not in line:
            raise SkillError(f"invalid YAML scalar line {i + 1}; install PyYAML for full YAML support")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value.startswith((">", "|")):
            folded = value.startswith(">")
            pieces = []
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i][0].isspace()):
                pieces.append(lines[i].strip())
                i += 1
            result[key] = (" " if folded else "\n").join(s for s in pieces if s)
            continue
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise SkillError(f"unclosed quoted YAML scalar at line {i + 1}")
            if value[0] == '"':
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as e:
                    raise SkillError(f"invalid quoted string: {e}") from e
            else:
                value = value[1:-1].replace("''", "'")
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        if key == "metadata" and value == "":
            result[key] = {}  # no-dependency fallback need not interpret metadata values
        else:
            result[key] = value
        i += 1
    return result


def load_skill(path: Path, root: Path, strict: bool = False) -> tuple[Skill, list[str]]:
    """Parse one SKILL.md. Returns (skill, warnings).

    `strict=True` turns advisory warnings into hard failures, for `lint --strict`.
    By default a spec deviation that still yields a usable name/description is a
    warning, not a drop: on a real 186-skill library, rejecting 27 skills whose
    folder name carries a marketplace suffix would silently hide a seventh of
    the inventory from routing.
    """
    metadata = _frontmatter(path)
    name, description = metadata.get("name"), metadata.get("description")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or len(name) > 64:
        raise SkillError("invalid name: use 1-64 lowercase letters/digits/hyphens, no adjacent hyphens")

    warnings: list[str] = []
    # The spec says name must match the parent directory. Real installs often
    # violate it (`foo__skillhub`, `foo-skill`, `skill_<id>`), so report, don't drop.
    if name != path.parent.name:
        message = f"name {name!r} differs from directory {path.parent.name!r} (spec requires a match)"
        if strict:
            raise SkillError(message)
        warnings.append(message)

    if isinstance(description, str):
        description = description.strip()
    if not isinstance(description, str) or not 1 <= len(description) <= 1024:
        raise SkillError("description must be a non-empty string of at most 1024 characters")

    compatibility = metadata.get("compatibility")
    if compatibility is not None and (not isinstance(compatibility, str) or len(compatibility) > 500):
        raise SkillError("compatibility must be a string of at most 500 characters")
    license_value = metadata.get("license")
    if license_value is not None and not isinstance(license_value, str):
        raise SkillError("license must be a string")
    extra = metadata.get("metadata")
    if extra is not None and not isinstance(extra, dict):
        raise SkillError("metadata must be a mapping")
    allowed_tools = metadata.get("allowed-tools")
    if allowed_tools is not None and not isinstance(allowed_tools, str):
        # Tolerate the list form some authors write; it still parses as intent.
        if isinstance(allowed_tools, list) and all(isinstance(x, str) for x in allowed_tools):
            warnings.append("allowed-tools is a list; the spec defines a space-separated string")
        else:
            raise SkillError("allowed-tools must be a string")

    return Skill(name, description, str(path.absolute()), str(root.absolute())), warnings


def default_roots(cwd: Path) -> list[Path]:
    roots: list[Path] = []
    # Current project only, plus conventional per-user locations.
    for base in [cwd, *list(cwd.parents)[:3]]:
        for suffix in (".agents/skills", ".claude/skills", "skills"):
            roots.append(base / suffix)
    home = Path.home()
    roots += [home / ".agents/skills", home / ".claude/skills", home / ".workbuddy/skills"]
    # Plugin/skillhub caches nest deeper (<vendor>/<plugin>/<version>/SKILL.md);
    # without this root a butler would report ~186 skills while the host actually
    # exposes ~90 more that it can never route to.
    roots += [home / ".workbuddy/plugins/cache", home / ".claude/plugins/cache"]
    roots += [Path(x).expanduser() for x in os.getenv("SKILL_PATHS", "").split(os.pathsep) if x.strip()]
    return list(dict.fromkeys(roots))


def _skill_files(root: Path, max_depth: int = 3) -> list[Path]:
    """Return SKILL.md files under `root`.

    Supports both layouts: `root/SKILL.md` (the root itself is one skill) and
    `root/<name>/SKILL.md` (a directory of skills). The default depth of 3 also
    catches plugin layouts such as
    `cache/<vendor>/<plugin>/<version>/SKILL.md`, which a strict one-level walk
    misses entirely — on this machine that is ~90 further skills. Symlinked
    entries are skipped at every level, and the walk stays bounded: no
    unbounded filesystem recursion.
    """
    direct = root / "SKILL.md"
    if direct.is_file():
        return [direct]

    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_symlink() or not child.is_dir():
                continue
            marker = child / "SKILL.md"
            if marker.is_file():
                found.append(marker)
            else:
                walk(child, depth + 1)

    walk(root, 1)
    return found


def discover(roots: list[Path], strict: bool = False) -> tuple[list[Skill], list[dict[str, str]]]:
    skills: list[Skill] = []
    issues: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for root in roots:
        root = root.expanduser()
        if not root.exists():
            continue
        if root.is_symlink():
            issues.append({"path": str(root), "error": "symlinked skill roots are not scanned"})
            continue
        if not root.is_dir():
            issues.append({"path": str(root), "error": "not a directory"})
            continue
        # Bounded discovery (max_depth=2), never an unbounded filesystem walk.
        for p in _skill_files(root):
            if p.is_symlink() or p.parent.is_symlink():
                issues.append({"path": str(p), "error": "symlink skipped"})
                continue
            key = str(p.resolve())
            if key in seen_paths:
                continue
            seen_paths.add(key)
            try:
                skill, warnings = load_skill(p, root, strict=strict)
            except SkillError as e:
                issues.append({"path": str(p), "error": str(e)})
                continue
            skills.append(skill)
            # Advisory deviations stay visible without dropping the skill.
            for message in warnings:
                issues.append({"path": str(p), "error": message, "severity": "warning"})
    names: dict[str, str] = {}
    for item in skills:
        if item.name in names:
            issues.append({"path": item.path, "error": f"duplicate name also found at {names[item.name]} (candidate retained; disambiguate before use)"})
        else:
            names[item.name] = item.path
    return skills, issues


def _tokens(value: str) -> set[str]:
    return {x.lower() for x in WORD_RE.findall(value.lower()) if x.lower() not in STOPWORDS}


def rank(task: str, skill: Skill) -> tuple[int, list[str]]:
    question = task.lower()
    identity = skill.name.replace("-", " ").lower()
    blob = f"{identity} {skill.description.lower()}"
    task_tokens = _tokens(question)
    skill_tokens = _tokens(blob)
    match = task_tokens & skill_tokens
    score = min(28, 7 * len(match))
    reasons = ["overlap:" + ",".join(sorted(match)[:6])] if match else []
    for category, terms in DOMAIN_ALIASES.items():
        task_has = any(term in question for term in terms)
        skill_has = any(term in blob for term in terms)
        if task_has and skill_has:
            # A passing reference in the description is weaker than domain ownership
            # expressed in the skill name (e.g. a PDF tool might mention "images").
            name_has = any(term in skill.name.replace("-", " ") for term in terms)
            score += 24 if name_has else 10
            reasons.append("domain:" + category + (":name" if name_has else ":description"))
    # Exact name tokens earn precision but never bypasses skill instruction review.
    name_parts = _tokens(identity)
    if name_parts and name_parts <= task_tokens:
        score += 18
        reasons.append("name-keywords")
    if skill.name.replace("-", " ") in question or skill.name in question:
        score += 32
        reasons.append("explicit-name")
    return score, reasons


def route(task: str, skills: list[Skill], top: int, threshold: int) -> dict[str, Any]:
    ranked = []
    for skill in skills:
        if skill.name == SELF_NAME:
            continue
        score, reasons = rank(task, skill)
        if score >= threshold:
            ranked.append({**asdict(skill), "score": score, "signals": reasons})
    ranked.sort(key=lambda r: (-r["score"], r["name"], r["path"]))
    found = ranked[:top]
    return {
        "status": "candidates" if found else "no_match",
        "candidate_count": len(ranked),
        "candidates": found,
        "selection_method": "heuristic_retrieval_only",
        "semantic_review_required": True,
        "actual_invocation_verified": False,
        "next_action": "Read the relevant candidate SKILL.md in full, verify scope/tools/permissions, and invoke via your host's actual skill/tool mechanism. If none fits, use ordinary tools or explain the blocker.",
    }


def _roots(args: argparse.Namespace) -> list[Path]:
    return [Path(r) for r in args.root] if args.root else default_roots(Path.cwd())


# --- Session scoping ---------------------------------------------------------
# A session manifest restricts which skills may be *considered* this session, so
# a focused task does not drag every installed skill into the routing context.

SESSION_MANIFEST_NAMES = ("aletheia-session.json", ".aletheia-session.json")
# Named allowlists so a recurring workflow does not need its scope retyped.
PROFILE_DIR_NAME = ".aletheia"


def load_profile(name: str, base: Path | None = None) -> list[str]:
    """Load a named allowlist from <base>/.aletheia/profiles/<name>.json.

    The file holds either a list of skill names or {"only": [...]}. Kept tiny on
    purpose: a profile that enables most of the library is not a profile.
    """
    root = (base or Path.cwd()).resolve()
    for directory in [root, *root.parents][:4]:
        candidate = directory / PROFILE_DIR_NAME / "profiles" / f"{name}.json"
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise SkillError(f"invalid profile {candidate}: {e}") from e
            names = data.get("only") if isinstance(data, dict) else data
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                raise SkillError(f"profile {candidate} must be a list of skill names or {{\"only\": [...]}}")
            return names
    raise SkillError(f"profile {name!r} not found (expected {PROFILE_DIR_NAME}/profiles/{name}.json)")


def parse_scope(values: list[str] | None) -> set[str] | None:
    """Parse --only / --scope-into a set of allowed skill names.

    Returns None when no restriction was requested (all skills allowed).
    Accepts comma or space separated names and tolerates repeated flags.
    """
    if not values:
        return None
    names: set[str] = set()
    for value in values:
        for part in re.split(r"[,\s]+", value.strip()):
            if part:
                names.add(part)
    return names or None


def load_session_manifest(explicit: Path | None, start: Path | None = None) -> dict[str, Any] | None:
    """Find an optional session manifest. Explicit path wins; else search upward."""
    if explicit is not None:
        path = explicit.expanduser()
        if not path.is_file():
            raise SkillError(f"session manifest not found: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise SkillError(f"invalid session manifest {path}: {e}") from e
        if not isinstance(data, dict):
            raise SkillError("session manifest must be a JSON object")
        data["_path"] = str(path)
        return data
    base = (start or Path.cwd()).resolve()
    for directory in [base, *base.parents][:4]:
        for name in SESSION_MANIFEST_NAMES:
            candidate = directory / name
            if candidate.is_file():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    raise SkillError(f"invalid session manifest {candidate}: {e}") from e
                if not isinstance(data, dict):
                    raise SkillError("session manifest must be a JSON object")
                data["_path"] = str(candidate)
                return data
    return None


def apply_scope(skills: list[Skill], allowed: set[str] | None) -> tuple[list[Skill], list[str]]:
    """Restrict `skills` to the allowlist. Returns (kept, suppressed_names)."""
    if allowed is None:
        return skills, []
    kept = [s for s in skills if s.name in allowed]
    suppressed = sorted(s.name for s in skills if s.name not in allowed)
    return kept, suppressed


def scope_report(
    skills: list[Skill],
    kept: list[Skill],
    suppressed: list[str],
    allowed: set[str] | None,
    manifest_path: str | None,
    detail: bool = False,
) -> dict[str, Any]:
    """Summarize the scope decision *without* re-spending the context it saves.

    A real inventory runs to ~190 skills. Printing every suppressed name costs
    kilobytes and hands most of the saving straight back, defeating the purpose
    of scoping. So the default reports a count; pass `detail=True` to get names.
    """
    if allowed is None:
        return {"active": False, "visible": len(skills), "suppressed_count": 0, "manifest": None}

    # Allowlist entries that matched nothing are the common silent failure: a
    # typo, or a skill that failed metadata lint and is therefore invisible.
    matched = {s.name for s in kept}
    unmatched = sorted(allowed - matched)

    # Name+description metadata is what occupies context each turn.
    def meta_size(items: list[Skill]) -> int:
        return sum(len(s.name) + len(s.description) + 40 for s in items)

    all_meta, kept_meta = meta_size(skills), meta_size(kept)
    saved = max(0, all_meta - kept_meta)

    report: dict[str, Any] = {
        "active": True,
        "visible": len(kept),
        "suppressed_count": len(suppressed),
        "manifest": manifest_path,
        "context_estimate": {
            "unit": "bytes_of_metadata",
            "unscoped": all_meta,
            "scoped": kept_meta,
            "saved_bytes": saved,
            "saved_percent": round(saved / all_meta * 100, 1) if all_meta else 0.0,
            "caveat": "Estimate over name+description metadata; actual host cost also includes any references read.",
        },
    }
    if unmatched:
        report["unmatched_allowed"] = unmatched
        report["warning"] = (
            f"{len(unmatched)} allowed skill(s) matched nothing — check spelling, or whether the skill "
            "failed metadata lint and is therefore not discoverable."
        )
    if detail:
        report["suppressed_skills"] = suppressed
    return report


# --- Context pressure --------------------------------------------------------
# No host exposes reliable token telemetry through this CLI, so pressure is
# estimated from *measured* on-disk transcript bytes. The result is explicitly
# labelled an estimate; never present it as a measured context-window percentage.

# Rough bytes-per-token across mixed CJK/English prose. Deliberately conservative.
BYTES_PER_TOKEN = 3.0
# Assumed window when the host does not report one. Overridable via --window.
DEFAULT_WINDOW_TOKENS = 128_000
# Transcript formats we can measure without executing anything.
TRANSCRIPT_GLOBS = (
    "**/*.jsonl",
    "**/session*.json",
    "**/transcript*.json",
    "**/*conversation*.json",
)

HOST_COMMANDS = {
    "claude": {
        "label": "Claude Code",
        "compact": "/compact",
        "new_session": "/clear",
        "hint": "/compact summarizes the current conversation and frees context; /clear starts fresh.",
    },
    "codex": {
        "label": "Codex",
        "compact": "/compact",
        "new_session": "/new",
        "hint": "/compact keeps the session but condenses history; /new starts a clean session.",
    },
    "workbuddy": {
        "label": "WorkBuddy",
        "compact": "/compact",
        "new_session": "/new",
        "hint": "Use /compact to summarize before continuing, or open a new chat when the task changes.",
    },
    "generic": {
        "label": "Generic agent host",
        "compact": "host-native compact/summarize command",
        "new_session": "start a new conversation",
        "hint": "Summarize the current goal, completed steps and open files, then begin a new conversation.",
    },
}

# notice -> trim -> new session, keyed by estimated utilization.
PRESSURE_TIERS = (
    (0.70, "ok", "Context pressure is low. No action needed."),
    (0.85, "notice", "Context is filling up. Consider compacting before the next large task."),
    (1.00, "trim", "Context is under pressure. Compact now to avoid dropping earlier constraints."),
)


def measure_transcript_bytes(root: Path, since_minutes: float | None = None) -> tuple[int, list[str]]:
    """Sum on-disk bytes of readable session transcripts. Read-only, no parsing."""
    total = 0
    seen: list[str] = []
    cutoff = (time.time() - since_minutes * 60) if since_minutes else None
    for pattern in TRANSCRIPT_GLOBS:
        for path in sorted(root.glob(pattern)):
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                if cutoff is not None and path.stat().st_mtime < cutoff:
                    continue
                size = path.stat().st_size
            except OSError:
                continue
            total += size
            seen.append(path.name)
    return total, seen[:10]


def context_pressure(root: Path, host: str, window_tokens: int, since_minutes: float | None) -> dict[str, Any]:
    total_bytes, files = measure_transcript_bytes(root, since_minutes)
    est_tokens = int(total_bytes / BYTES_PER_TOKEN)
    ratio = est_tokens / window_tokens if window_tokens else 0.0
    tier_name, advice = "new_session", "Context is likely exhausted. Start a new session and carry over a summary."
    for threshold, name, message in PRESSURE_TIERS:
        if ratio < threshold:
            tier_name, advice = name, message
            break
    host_key = host if host in HOST_COMMANDS else "generic"
    commands = HOST_COMMANDS[host_key]
    return {
        "status": tier_name,
        "measurement": "estimated_from_transcript_bytes",
        "is_measured_context_percentage": False,
        "caveat": (
            "No host token telemetry is available to this CLI. The percentage below is an "
            "estimate derived from on-disk transcript size, not a reading from the context window."
        ),
        "transcript_bytes": total_bytes,
        "estimated_tokens": est_tokens,
        "assumed_window_tokens": window_tokens,
        "estimated_utilization_percent": round(min(ratio, 9.99) * 100, 1),
        "files_sampled": files,
        "host": commands,
        "suggested_command": commands["compact"] if tier_name in ("notice", "trim") else commands["new_session"],
        "advice": advice,
    }


# --- Progress reporting ------------------------------------------------------
# A progress bar is the easiest thing in an agent UI to turn into a lie: an
# estimate that drifts, a bar that jumps 90% then stalls, an ETA nobody can
# support. Aletheia only renders progress that is *countable* — completed steps
# out of a declared total — and never invents a time estimate.

# Glyph sets: Unicode first, ASCII fallback for terminals without box drawing.
GLYPHS_UNICODE = {"full": "█", "partial": "▓", "empty": "░", "ok": "✓", "arrow": "→"}
GLYPHS_ASCII = {"full": "#", "partial": "=", "empty": ".", "ok": "[ok]", "arrow": "->"}

# Task states. "blocked" is deliberately distinct from "failed": waiting for a
# human decision is a healthy pause, not an error, and must not read as one.
PROGRESS_STATES = ("working", "blocked", "done", "failed")


def render_bar(fraction: float, width: int = 24, glyphs: dict[str, str] | None = None) -> str:
    """Render a proportional bar. Uses a partial block for sub-cell accuracy."""
    g = glyphs or GLYPHS_UNICODE
    fraction = max(0.0, min(1.0, fraction))
    exact = fraction * width
    full_cells = int(exact)
    remainder = exact - full_cells
    partial = g["partial"] if remainder >= 0.5 and full_cells < width else ""
    bar = g["full"] * full_cells + partial
    bar += g["empty"] * (width - len(bar))
    return f"[{bar}]"


def build_progress(
    steps: list[str],
    done: int,
    state: str = "working",
    width: int = 24,
    current: str | None = None,
    note: str | None = None,
    ascii_only: bool = False,
) -> dict[str, Any]:
    """Build a progress report from a *declared* step list.

    `done` counts steps that genuinely finished. There is deliberately no ETA
    field: an agent cannot know how long the next step will take, and a wrong
    ETA is worse than none.
    """
    if state not in PROGRESS_STATES:
        raise SkillError(f"unknown state {state!r}; use one of {', '.join(PROGRESS_STATES)}")
    total = len(steps)
    if total == 0:
        raise SkillError("declare at least one step so progress is countable")
    done = max(0, min(int(done), total))
    fraction = done / total
    glyphs = GLYPHS_ASCII if ascii_only else GLYPHS_UNICODE

    markers = []
    for index, step in enumerate(steps):
        if index < done:
            markers.append({"step": step, "status": "done"})
        elif index == done and state == "working":
            markers.append({"step": step, "status": "current"})
        elif index == done and state in ("blocked", "failed"):
            markers.append({"step": step, "status": state})
        else:
            markers.append({"step": step, "status": "pending"})

    if state == "done":
        headline = "Complete"
    elif state == "blocked":
        headline = "Waiting on you"
    elif state == "failed":
        headline = "Stopped"
    else:
        headline = current or (steps[done] if done < total else "")

    label = f"{glyphs['ok']} {done}/{total}" if state == "done" else f"{done}/{total}"
    line = f"{render_bar(fraction, width, glyphs)} {round(fraction * 100):>3}%  {label}"
    if headline and state != "done":
        line += f"  {glyphs['arrow']} {headline}"

    payload: dict[str, Any] = {
        "state": state,
        "bar": render_bar(fraction, width, glyphs),
        "percent": round(fraction * 100),
        "completed": done,
        "total": total,
        "line": line,
        "steps": markers,
        "eta": None,
        "eta_note": "No time estimate is available; an agent cannot know how long the next step takes.",
        "countable": True,
    }
    if note:
        payload["note"] = note
    return payload


# --- Inventory: the butler's registry view ----------------------------------

def build_inventory(
    skills: list[Skill],
    issues: list[dict[str, str]],
    roots: list[Path],
    query: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Full registry with stable numbers the owner can pick from.

    Numbers are 1-based over the *filtered* list, so the agent can quote them
    verbatim. Stability is per-invocation: re-running after a skill is installed
    renumbers everything, so always quote the list the user is looking at.
    """
    pool = skills
    if query:
        terms = {t for t in re.split(r"[\s,]+", query.lower()) if t}
        pool = [s for s in pool if any(t in f"{s.name} {s.description}".lower() for t in terms)]

    # The same skill is often installed twice (personal dir + plugin cache).
    # Collapse duplicates so a quoted number never points at an ambiguous pair.
    seen_names: set[str] = set()
    deduped: list[Skill] = []
    duplicates: list[dict[str, Any]] = []
    for candidate in sorted(pool, key=lambda s: s.name):
        if candidate.name in seen_names:
            duplicates.append({"name": candidate.name, "also_at": candidate.path})
            continue
        seen_names.add(candidate.name)
        deduped.append(candidate)

    ordered = deduped
    shown = ordered[:limit] if limit > 0 else ordered
    entries = [
        {"n": index, "name": s.name, "description": s.description, "path": s.path}
        for index, s in enumerate(shown, start=1)
    ]

    warnings = [i for i in issues if i.get("severity") == "warning"]
    errors = [i for i in issues if i.get("severity") != "warning"]

    return {
        "total_installed": len(skills),
        "unique_skills": len(ordered),
        "duplicate_installs": len(duplicates),
        "duplicate_sample": duplicates[:5],
        "matched": len(ordered),
        "listed": len(entries),
        "truncated": len(ordered) > len(entries),
        "entries": entries,
        "roots_checked": [str(p) for p in roots],
        "warnings": {"count": len(warnings), "sample": [w["error"] for w in warnings[:5]]},
        "errors": {"count": len(errors), "sample": [e["error"] for e in errors[:5]]},
        "context_estimate_bytes": sum(len(s.name) + len(s.description) + 40 for s in ordered),
        "how_to_pick": (
            "Reply with one or more numbers ('2', '2,5', '2 5'), or 'all' / 'none'. "
            "In auto mode Aletheia chooses and shows its reasoning instead."
        ),
    }


def load_mode_config(path: Path | None) -> dict[str, Any]:
    """Read the persisted owner preference (auto vs manual)."""
    config = {"mode": "auto"}
    if path is None or not path.is_file():
        return config
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return config
    if isinstance(data, dict):
        mode = data.get("mode")
        if mode in ("auto", "manual"):
            config["mode"] = mode
        if isinstance(data.get("only"), list):
            config["only"] = [s for s in data["only"] if isinstance(s, str)]
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only, local Agent Skills discovery & routing hints")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "route", "lint"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", action="append", default=[], help="skill parent directory, repeatable; no root means conventional local paths")
        cmd.add_argument("--json", action="store_true", help="machine-readable output (default for route)")
        cmd.add_argument("--only", action="append", default=[], help="restrict to these skill names (comma/space separated)")
        cmd.add_argument("--session", type=Path, default=None, help="session manifest JSON restricting this session's skills")
        cmd.add_argument("--scope-detail", action="store_true", help="list every suppressed skill name (costs context; default is a count)")
        cmd.add_argument("--profile", default=None, help="named allowlist from .aletheia/profiles/<name>.json")
        if name == "lint":
            cmd.add_argument("--strict", action="store_true", help="treat advisory warnings as failures")
        if name == "route":
            cmd.add_argument("task", help="user task text; avoid secrets, especially if logging command line")
            cmd.add_argument("--top", type=int, default=DEFAULT_TOP)
            cmd.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    ev = sub.add_parser("eval", help="evaluate retrieval against a JSON case file")
    ev.add_argument("--root", action="append", default=[])
    ev.add_argument("--cases", required=True)
    ev.add_argument("--only", action="append", default=[], help="restrict candidates to these skill names")

    ctx = sub.add_parser("context", help="estimate context pressure and suggest a host switch/compact command")
    ctx.add_argument("--transcripts", type=Path, default=None, help="directory containing session transcripts")
    ctx.add_argument("--host", choices=sorted(HOST_COMMANDS), default="generic")
    ctx.add_argument("--window", type=int, default=DEFAULT_WINDOW_TOKENS, help="assumed context window in tokens")
    ctx.add_argument("--since-minutes", type=float, default=None, help="only count transcripts modified recently")

    prog = sub.add_parser("progress", help="render a countable progress bar for a declared step list")
    prog.add_argument("steps", nargs="+", help="ordered task steps, e.g. gather read write verify")
    prog.add_argument("--done", type=int, default=0, help="how many steps genuinely finished")
    prog.add_argument("--state", choices=PROGRESS_STATES, default="working")
    prog.add_argument("--width", type=int, default=24, help="bar width in characters")
    prog.add_argument("--current", default=None, help="short label for what is happening right now")
    prog.add_argument("--note", default=None, help="one-line caveat, e.g. what is blocked")
    prog.add_argument("--ascii", action="store_true", help="ASCII glyphs for terminals without box drawing")

    inv = sub.add_parser("inventory", help="list every discovered skill with numbers the owner can pick from")
    inv.add_argument("--root", action="append", default=[])
    inv.add_argument("--query", default=None, help="filter by substring across name and description")
    inv.add_argument("--limit", type=int, default=50, help="max rows (0 for all)")
    inv.add_argument("--json", action="store_true", help="machine-readable output (default)")

    mode = sub.add_parser("mode", help="show or set the owner's auto/manual selection preference")
    mode.add_argument("--config", type=Path, default=None, help="config path (default aletheia-config.json)")
    mode.add_argument("--set", dest="new_mode", choices=("auto", "manual"), default=None, help="switch and persist")
    mode.add_argument("--only", action="append", default=[], help="with --set manual: initial allowlist of skill names")

    args = parser.parse_args(argv)

    if args.command == "inventory":
        roots = _roots(args)
        skills, issues = discover(roots)
        payload = build_inventory(skills, issues, roots, query=args.query, limit=args.limit)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "mode":
        config_path = (args.config or Path.cwd() / "aletheia-config.json").expanduser()
        if args.new_mode is None:
            print(json.dumps(load_mode_config(config_path), ensure_ascii=False, indent=2))
            return 0
        only = parse_scope(args.only)
        saved = {"mode": args.new_mode}
        if only:
            saved["only"] = sorted(only)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"saved": str(config_path), **saved}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "progress":
        try:
            payload = build_progress(
                args.steps,
                args.done,
                state=args.state,
                width=max(4, min(args.width, 80)),
                current=args.current,
                note=args.note,
                ascii_only=args.ascii,
            )
        except SkillError as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
            return 2
        print(payload["line"])
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "context":
        transcripts = args.transcripts.expanduser() if args.transcripts else Path.home()
        if not transcripts.is_dir():
            print(json.dumps({"error": f"transcript directory not found: {transcripts}"}, indent=2))
            return 2
        if args.window <= 0:
            parser.error("--window must be > 0")
        print(json.dumps(context_pressure(transcripts, args.host, args.window, args.since_minutes), ensure_ascii=False, indent=2))
        return 0

    roots = _roots(args)
    strict_lint = args.command == "lint" and getattr(args, "strict", False)
    skills, issues = discover(roots, strict=strict_lint)

    # Session scoping narrows candidates; it is a routing filter, not a security boundary.
    scope_manifest = None
    scope_names: set[str] | None = None
    if args.command == "eval":
        scope_names = parse_scope(args.only)
    elif args.command in ("scan", "route", "lint"):
        manifest_path = getattr(args, "session", None)
        profile_name = getattr(args, "profile", None)
        try:
            scope_manifest = load_session_manifest(manifest_path)
            profile_names = load_profile(profile_name) if profile_name else None
        except SkillError as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
            return 2
        if scope_manifest is not None:
            declared = scope_manifest.get("only") or scope_manifest.get("allowed_skills")
            scope_names = parse_scope(declared if isinstance(declared, list) else ([declared] if isinstance(declared, str) else None))
        if profile_names:
            from_profile = parse_scope(profile_names)
            scope_names = from_profile if scope_names is None else (scope_names & from_profile)
        explicit = parse_scope(getattr(args, "only", None))
        if explicit:
            scope_names = explicit if scope_names is None else (scope_names & explicit)

    # Keep the pre-scope inventory so the saving can be quantified honestly.
    kept_before_scope = skills
    suppressed: list[str] = []
    if scope_names is not None:
        skills, suppressed = apply_scope(skills, scope_names)

    # Report the decision compactly; `--scope-detail` opts back into full names.
    scope_detail = bool(getattr(args, "scope_detail", False))
    scope_payload = scope_report(
        skills if scope_names is None else kept_before_scope,
        skills,
        suppressed,
        scope_names,
        scope_manifest.get("_path") if scope_manifest else None,
        detail=scope_detail,
    )
    if scope_names is not None:
        scope_payload["allowed_skills"] = sorted(scope_names)
    if getattr(args, "profile", None):
        scope_payload["profile"] = args.profile

    if args.command == "scan":
        payload = {"skills": [asdict(s) for s in skills], "issues": issues, "roots_checked": [str(p) for p in roots], "scope": scope_payload}
    elif args.command == "lint":
        payload = {"valid": len(skills), "invalid_or_warnings": issues, "ok": not issues, "scope": scope_payload}
    elif args.command == "route":
        if args.top <= 0 or args.threshold < 0:
            parser.error("--top must be > 0; --threshold must be >= 0")
        payload = route(args.task, skills, args.top, args.threshold)
        payload["issues"] = issues
        payload["scope"] = scope_payload
    else:
        try:
            cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
            assert isinstance(cases, list)
        except (OSError, ValueError, AssertionError) as e:
            parser.error(f"invalid case file: {e}")
        details = []
        passed = 0
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("task"), str) or not isinstance(case.get("expect"), list):
                parser.error("each case must have task:string and expect:string[]")
            results = route(case["task"], skills, EVAL_TOP, DEFAULT_THRESHOLD)
            got = [s["name"] for s in results["candidates"]]
            want = case["expect"]
            ok = set(want).issubset(set(got)) if want else not got
            passed += int(ok)
            details.append({"id": case.get("id"), "pass": ok, "expected": want, "top3": got})
        payload = {"cases": len(details), "passed": passed, "pass_rate": round(passed / len(details), 3) if details else None, "details": details, "warning": "This measures candidate retrieval, not actual skill invocation or task quality.", "issues": issues}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.command == "lint" and issues:
        return 1
    if args.command == "eval" and passed != len(details):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

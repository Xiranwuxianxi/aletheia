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

VERSION = "1.10.0"
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
    result: dict[str, Any] = {}
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
        # A key with an empty value followed by indented "- " items is a block
        # sequence. Collect it as a list instead of silently dropping the items,
        # so callers can see the real shape (e.g. a list-style allowed-tools)
        # rather than concluding the document is malformed.
        if value == "":
            items: list[str] = []
            j = i + 1
            while j < len(lines) and lines[j][:1].isspace() and lines[j].strip().startswith("- "):
                items.append(lines[j].strip()[2:].strip().strip("\"'"))
                j += 1
            if items:
                result[key] = items
                i = j
                continue
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
    roots += [home / ".agents/skills", home / ".claude/skills"]
    # Plugin/skillhub caches nest deeper (<vendor>/<plugin>/<version>/SKILL.md);
    # without this root a butler would report ~186 skills while the host actually
    # exposes ~90 more that it can never route to.
    roots += [home / ".workbuddy/plugins/cache", home / ".claude/plugins/cache"]
    # Every supported host's own skill directory, so skills installed under a
    # different agent are still visible to the butler.
    roots += host_skill_roots()
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


# --- Metering ---------------------------------------------------------------
# Everything here is a COUNT of something observable on disk. There is no token
# telemetry on most hosts, so this module never invents one. Fields it cannot
# measure are recorded as the string "unavailable", never as a plausible number.
#
# The distinction is load-bearing:
#   measured   — read from the filesystem right now, reproducible
#   estimated  — derived by a documented rule from measured values
#   unavailable — the host exposes nothing; deliberately left blank

UNAVAILABLE = "unavailable"

# Bytes-per-token by script type. Mixed CJK prose runs ~1.5-2 B/token; English
# code and JSON run ~3.5-4 B/token. These are conservative midpoints and are
# always reported as estimates, never as usage.
TOKEN_BYTES_BY_SCRIPT = {
    "cjk_mixed": 2.0,
    "latin_code": 3.5,
}

LEDGER_DIR_NAME = ".aletheia"
LEDGER_FILE_NAME = "ledger.jsonl"


def ledger_path(base: Path | None = None) -> Path:
    """Local ledger location. Stays on this machine; never uploaded."""
    return (base or Path.home()) / LEDGER_DIR_NAME / LEDGER_FILE_NAME


def estimate_tokens(chars: int, script: str = "cjk_mixed") -> int:
    """Convert a measured character count into an estimated token count."""
    return int(chars / TOKEN_BYTES_BY_SCRIPT.get(script, 2.0))


def new_task_id() -> str:
    return time.strftime("task-%Y%m%dT%H%M%SZ", time.gmtime())


def append_ledger(record: dict[str, Any], base: Path | None = None) -> Path:
    """Append one measurement record. Local file only; no network, no telemetry."""
    path = ledger_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def read_ledger(base: Path | None = None) -> list[dict[str, Any]]:
    """Read ledger records. `base` may be a directory or the jsonl file itself."""
    if base is None:
        path = ledger_path()
    elif base.is_file() or base.suffix == ".jsonl":
        path = base
    else:
        path = base / LEDGER_FILE_NAME
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue  # a partially written line must not break reporting
    return records


def measure_routing_cost(
    task: str,
    skills: list[Skill],
    allowed: set[str] | None,
    top: int = DEFAULT_TOP,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Measure the real, reproducible cost of routing this one task.

    All numbers here are derived from files just read. The token figures are
    `estimated` because bytes-to-tokens is a conversion, not a host reading.
    """
    unscoped_chars = sum(len(s.name) + len(s.description) + 40 for s in skills)
    visible, suppressed = apply_scope(skills, allowed)
    scoped_chars = sum(len(s.name) + len(s.description) + 40 for s in visible)
    candidates = route(task, visible, top, threshold)["candidates"]
    # Only the selected skills' bodies are loaded; rejected ones cost nothing.
    selected_chars = sum(len(s.description) for s in visible if s.name in {c["name"] for c in candidates})

    return {
        "task_chars": len(task),
        "task_tokens_est": estimate_tokens(len(task)),
        "inventory_visible": len(visible),
        "inventory_total": len(skills),
        "metadata_chars_unscoped": unscoped_chars,
        "metadata_chars_scoped": scoped_chars,
        "metadata_tokens_est_unscoped": estimate_tokens(unscoped_chars),
        "metadata_tokens_est_scoped": estimate_tokens(scoped_chars),
        "metadata_tokens_saved_est": max(0, estimate_tokens(unscoped_chars) - estimate_tokens(scoped_chars)),
        "candidates": [{"name": c["name"], "score": c["score"]} for c in candidates],
        "selected_desc_chars": selected_chars,
        "selected_desc_tokens_est": estimate_tokens(selected_chars),
        "fields": {
            "task_tokens": "estimated",
            "metadata_tokens": "estimated",
            "host_token_usage": UNAVAILABLE,
            "host_token_note": (
                "This host exposes no token telemetry. Actual prompt/completion tokens cannot be "
                "measured from here; ask the host UI or API response for real usage."
            ),
        },
    }


def compare_scenarios(baseline: dict[str, Any], scoped: dict[str, Any]) -> dict[str, Any]:
    """Compare 'no aletheia' against 'aletheia + scoping'.

    Honest framing matters more than a big number: without routing, an agent
    either (a) loads every installed skill's metadata, or (b) improvises and may
    pick the wrong skill and redo the work. Only (a) is measurable here, so only
    (a) is quantified.
    """
    saved = max(0, baseline["metadata_tokens_est_unscoped"] - scoped["metadata_tokens_est_scoped"])
    ratio = (
        saved / baseline["metadata_tokens_est_unscoped"] * 100
        if baseline["metadata_tokens_est_unscoped"] else 0.0
    )
    return {
        "comparison": {
            "without_aletheia": {
                "label": "No routing, whole library visible",
                "metadata_tokens_est": baseline["metadata_tokens_est_unscoped"],
                "basis": "measured chars -> estimated tokens",
            },
            "with_aletheia_scoped": {
                "label": "Aletheia with an allowlist",
                "metadata_tokens_est": scoped["metadata_tokens_est_scoped"],
                "basis": "measured chars -> estimated tokens",
            },
            "saved_tokens_est": saved,
            "saved_percent": round(ratio, 1),
        },
        "not_quantified": [
            {
                "claim": "tokens saved by not redoing the wrong skill",
                "value": UNAVAILABLE,
                "why": "Requires a real A/B run on the same task. The CLI cannot know how much "
                       "work a wrong skill caused, and guessing would be fabrication.",
            },
            {
                "claim": "actual host token usage with vs without",
                "value": UNAVAILABLE,
                "why": "No token telemetry on this host. Read it from the host's own UI or API response.",
            },
            {
                "claim": "money saved",
                "value": UNAVAILABLE,
                "why": "Requires a per-token price and a measured billable token count; neither is available here.",
            },
        ],
        "how_to_get_real_numbers": [
            "Run the same task twice in the host: once normally, once with a scoped allowlist.",
            "Read the token usage the host reports at the end of each run.",
            "Record both with: router.py measure --task-id <id> --label <run> --actual-tokens <n>",
        ],
    }


def render_report_html(records: list[dict[str, Any]]) -> str:
    """Render a self-contained HTML comparison report.

    Design rule: measured, estimated and unavailable look different, and every
    estimate carries its basis. A number without a visible provenance label is
    the thing this project exists to prevent.
    """
    if not records:
        rows = '<tr><td colspan="6" class="empty">No measurements recorded yet.</td></tr>'
    else:
        rows = ""
        for rec in records:
            with_a = rec.get("with_aletheia", {})
            without = rec.get("without_aletheia", {})
            actual = rec.get("actual_tokens", UNAVAILABLE)
            # A telemetry record has no per-task cost columns; show that honestly
            # instead of inventing zeros for it.
            if "metadata_tokens_est_unscoped" in without:
                no_col = f"{without['metadata_tokens_est_unscoped']:,}"
                yes_col = f"{with_a.get('metadata_tokens_est_scoped', 0):,}"
            else:
                no_col = yes_col = '<span class="na">n/a</span>'
            actual_cell = (
                f"{actual:,}" if isinstance(actual, int)
                else '<span class="na">not measurable here</span>'
            )
            label = _esc(rec.get("label", ""))[:44]
            rows += (
                "<tr>"
                f"<td class=\"mono\">{_esc(rec.get('task_id', ''))}</td>"
                f"<td><span class=\"tag {_esc(rec.get('phase', ''))}\">{_esc(rec.get('phase', ''))}</span></td>"
                f"<td class=\"mono\">{label}</td>"
                f"<td class=\"num\">{no_col}<span class=\"est\">est</span></td>"
                f"<td class=\"num\">{yes_col}<span class=\"est\">est</span></td>"
                f"<td class=\"num\">{actual_cell}</td>"
                "</tr>"
            )

    host_cards = ""
    telemetry = {}
    for rec in reversed(records):
        if rec.get("host_telemetry"):
            telemetry = rec["host_telemetry"]
            break
    for host, info in telemetry.items():
        label = _esc(info.get("label", host))
        if info.get("available"):
            def num(key: str, _info: dict = info) -> str:
                value = _info.get(key)
                return f"{value:,}" if isinstance(value, int) else _esc(value)

            host_cards += (
                '<div class="card measured-card">'
                f'<h3>{label} <span class="ok">measured</span></h3>'
                f'<p class="big">{num("total_tokens_including_cache_read")}</p>'
                f'<p class="why">input {num("input_tokens")} · output {num("output_tokens")}'
                f' · cache read {num("cache_read_tokens")}'
                f' · cache write {num("cache_write_tokens")}'
                f' · {_esc(info.get("messages_with_usage"))} messages across'
                f' {_esc(info.get("sessions_scanned"))} session file(s)</p>'
                "</div>"
            )
        else:
            host_cards += (
                '<div class="card na-card">'
                f"<h3>{label}</h3><p class=\"na\">unavailable</p>"
                f'<p class="why">{_esc(info.get("reason", ""))}</p>'
                "</div>"
            )

    not_quantified = ""
    for rec in reversed(records):
        items = rec.get("comparison", {}).get("not_quantified")
        if items:
            not_quantified = "".join(
                '<div class="card na-card">'
                f"<h3>{_esc(item['claim'])}</h3>"
                f'<p class="na">{_esc(item["value"])}</p>'
                f'<p class="why">{_esc(item["why"])}</p>'
                "</div>"
                for item in items
            )
            break

    last_cmp = _latest_comparison(records)
    last_without = records[-1].get("without_aletheia", {}) if records else {}
    last_with = records[-1].get("with_aletheia", {}) if records else {}
    without_tokens = last_cmp.get("without_aletheia", {}).get("metadata_tokens_est", "—")
    with_tokens = last_cmp.get("with_aletheia_scoped", {}).get("metadata_tokens_est", "—")
    saved = f"{last_cmp['saved_tokens_est']:,}" if "saved_tokens_est" in last_cmp else "—"
    saved_pct = f"{last_cmp['saved_percent']}%" if "saved_percent" in last_cmp else "—"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aletheia · routing cost report</title>
<style>
:root {{
  --bg:#fbfaf8; --card:#ffffff; --ink:#1f1d1a; --muted:#6b675f; --faint:#9a958c;
  --line:#e6e2da; --accent:#534AB7; --accent-soft:#eeedfe;
  --warn:#BA7517; --warn-soft:#FAEEDA; --na:#8a857c; --na-soft:#f2f0ec;
  --good:#0F6E56; --good-soft:#E1F5EE;
}}
*{{box-sizing:border-box}}
body{{margin:0;padding:32px 20px;background:var(--bg);color:var(--ink);
  font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
.wrap{{max-width:940px;margin:0 auto}}
header{{margin-bottom:28px}}
h1{{font-size:20px;font-weight:600;margin:0 0 6px;letter-spacing:-.01em}}
.sub{{color:var(--muted);font-size:13px;margin:0}}
.brand{{display:inline-flex;align-items:center;gap:8px;margin-bottom:14px}}
.mark{{width:26px;height:26px;border-radius:7px;background:var(--accent);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600}}
.legend{{display:flex;gap:16px;flex-wrap:wrap;margin:20px 0 12px;font-size:12.5px;color:var(--muted)}}
.legend span{{display:inline-flex;align-items:center;gap:6px}}
.dot{{width:8px;height:8px;border-radius:50%}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:28px}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}}
.stat .label{{font-size:12.5px;color:var(--muted);margin:0 0 4px}}
.stat .value{{font-size:26px;font-weight:600;letter-spacing:-.02em}}
.stat .note{{font-size:11.5px;color:var(--faint);margin:4px 0 0}}
.good .value{{color:var(--good)}}
table{{width:100%;border-collapse:collapse;background:var(--card);
  border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13px}}
th{{text-align:left;padding:11px 14px;background:var(--accent-soft);color:var(--accent);
  font-weight:600;font-size:12px}}
td{{padding:11px 14px;border-top:1px solid var(--line);vertical-align:top}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.empty{{text-align:center;color:var(--faint);padding:32px}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}}
.tag{{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600}}
.tag.before{{background:var(--accent-soft);color:var(--accent)}}
.tag.after{{background:var(--good-soft);color:var(--good)}}
.est{{font-size:10px;color:var(--faint);margin-left:5px;vertical-align:super}}
.na{{color:var(--na);background:var(--na-soft);padding:1px 7px;border-radius:5px;font-size:12px}}
h2{{font-size:15px;font-weight:600;margin:32px 0 12px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 17px}}
.card h3{{font-size:13.5px;margin:0 0 7px;font-weight:600}}
.card p{{margin:0;font-size:12.5px}}
.why{{color:var(--muted);margin-top:7px!important}}
.ok{{font-size:10px;background:var(--good-soft);color:var(--good);padding:2px 7px;border-radius:99px;
  font-weight:600;vertical-align:middle}}
.measured-card .big{{font-size:22px;font-weight:600;margin:0 0 4px;color:var(--ink)}}
.foot{{font-size:12px;color:var(--faint);margin:10px 2px 0}}
.banner{{background:var(--warn-soft);border:1px solid #EF9F27;border-radius:12px;
  padding:14px 17px;margin:22px 0;font-size:13px;color:#633806}}
.banner strong{{color:#412402}}
footer{{margin-top:34px;padding-top:18px;border-top:1px solid var(--line);
  font-size:12px;color:var(--faint)}}
@media print{{body{{background:#fff;padding:0}} .card,.stat,table{{break-inside:avoid}}}}
</style></head><body><div class="wrap">

<div class="brand"><div class="mark">Α</div>
<div><h1>Routing cost report</h1>
<p class="sub">Local ledger · {len(records)} record(s) · generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}</p></div></div>

<div class="legend">
<span><span class="dot" style="background:var(--good)"></span> measured on disk</span>
<span><span class="dot" style="background:var(--warn)"></span> estimated from measured values</span>
<span><span class="dot" style="background:var(--na)"></span> unavailable — deliberately blank</span>
</div>

<div class="grid">
<div class="stat"><p class="label">Metadata tokens, no routing</p>
<p class="value">{without_tokens}</p>
<p class="note">estimated · whole library visible</p></div>
<div class="stat"><p class="label">Metadata tokens, scoped</p>
<p class="value">{with_tokens}</p>
<p class="note">estimated · allowlist applied</p></div>
<div class="stat good"><p class="label">Reduction</p>
<p class="value">{saved_pct}</p>
<p class="note">{saved} tokens estimated saved</p></div>
<div class="stat"><p class="label">Actual host tokens</p>
<p class="value" style="font-size:19px;color:var(--na)">see host report</p>
<p class="note">measured per host, not by this tool</p></div>
</div>

<div class="banner"><strong>Read this before quoting a number.</strong>
&nbsp;Metadata figures are <strong>estimates</strong> from a character count divided by a documented
bytes-per-token constant. They are reproducible and they are <em>not</em> host billing data. This host
exposes no prompt/completion token counter, so actual usage is left blank rather than guessed.</div>

<table><thead><tr><th>Task</th><th>Phase</th><th>Label</th>
<th class="num">No routing</th><th class="num">Scoped</th><th class="num">Actual</th></tr></thead>
<tbody>{rows}</tbody></table>

<h2>Actual host usage, read from session files</h2>
<div class="cards">{host_cards or '<div class="card"><p class="why">No telemetry recorded yet. Run <span class="mono">router.py telemetry --record &lt;ledger&gt;</span>.</p></div>'}</div>
<p class="foot">Cache reads are billed far below fresh input, so a blended rate would mislead. These
raw counts are the honest form; apply your own pricing.</p>

<h2>Deliberately not quantified</h2>
<div class="cards">{not_quantified or '<div class="card"><p class="why">Record a measurement first.</p></div>'}</div>

<h2>Getting real numbers</h2>
<div class="card"><ol style="margin:0;padding-left:18px;font-size:13px;color:var(--muted)">
<li>Run the same task twice in the host: once normally, once with a scoped allowlist.</li>
<li>Read the token usage the host itself reports at the end of each run.</li>
<li>Record it: <span class="mono">python skills/aletheia/scripts/router.py measure "task" --phase after --actual-tokens &lt;n&gt;</span></li>
</ol></div>

<footer>Aletheia · local ledger at <span class="mono">~/.aletheia/ledger.jsonl</span> · nothing leaves this machine ·
<strong>measured ≠ estimated ≠ available</strong></footer>

</div></body></html>"""


def _esc(value: Any) -> str:
    text = str(value)
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


# --- Cross-agent telemetry --------------------------------------------------
# Claude Code and Codex both persist real per-message usage in their session
# jsonl files. WorkBuddy does not. So "measured actual tokens" is available for
# some hosts and genuinely unavailable for others — which is exactly the split
# the report has to show rather than paper over.

# Each adapter: where sessions live, and which JSON shapes carry usage.
# Hosts nest differently: Claude Code puts it at message.usage, Codex at the
# top level. Both shapes are probed, because guessing wrong yields a confident
# zero — the exact failure this whole feature must never have.
# --- Multi-host telemetry registry -------------------------------------------
# Hosts disagree on almost everything: where sessions live, how deep they nest,
# where the usage block sits, and even what the fields are called. Verified
# against the layout each tool actually writes rather than assumed:
#
#   Claude Code   ~/.claude/projects/**/*.jsonl   message.usage
#                 {input_tokens, output_tokens, cache_read_input_tokens,
#                  cache_creation_input_tokens}
#   Codex         ~/.codex/**/*.jsonl              usage
#                 {input_tokens, output_tokens, input_token_details.cached_tokens}
#   Kimi Code     ~/.kimi/sessions/**/wire.jsonl   message.payload.token_usage
#                 {input_other, output, input_cache_read, input_cache_creation}
#   Qwen Code     ~/.qwen/projects/**/*.jsonl      usageMetadata (Gemini lineage)
#   Gemini CLI    $GEMINI_CLI_HOME/tmp/*/chats/*   usageMetadata
#   Copilot CLI   ~/.copilot/{otel,session-state} events.jsonl
#   OpenCode      ~/.local/share/opencode/storage/message/*.json
#   Droid         ~/.factory/sessions/*.settings.json
#   Kiro          ~/.kiro/sessions/cli/*.json
#   Crush         ~/.local/share/crush/projects.json
#
# `aliases` normalises each host's field names onto ours. A host with no entry
# here is reported unavailable — never zero.

# Canonical buckets every adapter maps onto.
TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write")

# Every literal that could introduce a usage block. Used only as a fast
# prefilter; missing one of these would silently drop real data.
USAGE_HINT_KEYS = (
    "usage", "usageMetadata", "token_usage", "tokens", "totals", "metrics",
    "prompt_tokens", "completion_tokens", "input_tokens", "output_tokens",
    "cache_read", "cacheRead", "cache_creation", "cacheWrite", "cached_tokens",
    "promptTokenCount", "candidatesTokenCount", "cachedContentTokenCount",
    # Short field names used by Kimi, OpenCode and Kiro. A line carrying only
    # these would otherwise be skipped before parsing.
    "input", "output", "promptToken", "completionToken",
    "cachedContent", "inputToken", "outputToken", "cacheWrite",
)


def _usage_prefilter(spec: dict[str, Any]) -> tuple[str, ...]:
    """Hints for one host: the shared set plus its own path segments and aliases.

    Deriving this from the adapter's own declaration means a newly added alias
    cannot be silently filtered out — the guard is structural, not a ritual.
    """
    extra: list[str] = []
    for path_tuple in spec.get("usage_paths", ()):
        extra.extend(p for p in path_tuple if p)
    for names in (spec.get("aliases") or {}).values():
        extra.extend(names)
    return tuple(dict.fromkeys(USAGE_HINT_KEYS + tuple(extra)))

TELEMETRY_HOSTS: dict[str, dict[str, Any]] = {
    "claude": {
        "label": "Claude Code",
        "sessions": "~/.claude/projects",
        "globs": ("**/*.jsonl",),
        "usage_paths": (("message", "usage"), ("usage",)),
        "aliases": {
            "input": ("input_tokens", "input_other"),
            "output": ("output_tokens", "output"),
            "cache_read": ("cache_read_input_tokens", "input_cache_read"),
            "cache_write": ("cache_creation_input_tokens", "input_cache_creation"),
        },
        "skills": ("~/.claude/skills",),
        "native_skill_dir": ".claude/skills",
    },
    "codex": {
        "label": "Codex",
        "sessions": "~/.codex",
        "globs": ("**/*.jsonl",),
        "usage_paths": (("usage",), ("message", "usage"), ("token_usage",)),
        "aliases": {
            "input": ("input_tokens", "input_other"),
            "output": ("output_tokens", "output"),
            "cache_read": ("cache_read_input_tokens", "input_cache_read"),
            "cache_write": ("cache_creation_input_tokens", "input_cache_creation"),
        },
        # Codex reports cache hits as a detail object, not a flat field.
        "cache_read_from": ("input_token_details", "cached_tokens"),
        "skills": ("~/.agents/skills",),
        "native_skill_dir": ".agents/skills",
    },
    "kimi": {
        "label": "Kimi Code",
        "sessions": "~/.kimi/sessions",
        "globs": ("**/wire.jsonl",),
        "usage_paths": (("message", "payload", "token_usage"), ("token_usage",)),
        "aliases": {
            "input": ("input_other", "input_tokens"),
            "output": ("output", "output_tokens"),
            "cache_read": ("input_cache_read", "cache_read_input_tokens"),
            "cache_write": ("input_cache_creation", "cache_creation_input_tokens"),
        },
        "skills": ("~/.kimi/skills", "~/.agents/skills"),
        "native_skill_dir": ".kimi/skills",
    },
    "qwen": {
        "label": "Qwen Code",
        "sessions": "~/.qwen/projects",
        "globs": ("**/*.jsonl",),
        "usage_paths": (("usageMetadata",), ("message", "usageMetadata"), ("usage",)),
        "aliases": {
            "input": ("promptTokenCount", "input_tokens", "input_other"),
            "output": ("candidatesTokenCount", "output_tokens", "output"),
            "cache_read": ("cachedContentTokenCount", "cache_read_input_tokens", "input_cache_read"),
            "cache_write": ("cache_creation_input_tokens", "input_cache_creation"),
        },
        "skills": ("~/.qwen/skills", "~/.agents/skills"),
        "native_skill_dir": ".qwen/skills",
    },
    "gemini": {
        "label": "Gemini CLI",
        "sessions": "~/.gemini/tmp",
        "globs": ("**/chats/*.json", "**/chats/*.jsonl"),
        "usage_paths": (("usageMetadata",), ("message", "usageMetadata"), ("tokens",)),
        "aliases": {
            "input": ("promptTokenCount", "input_tokens", "input_other"),
            "output": ("candidatesTokenCount", "output_tokens", "output"),
            "cache_read": ("cachedContentTokenCount", "cache_read_input_tokens"),
            "cache_write": ("cache_creation_input_tokens", "input_cache_creation"),
        },
        "skills": ("~/.gemini/extensions", "~/.agents/skills"),
        "native_skill_dir": ".gemini/extensions",
    },
    "copilot": {
        "label": "GitHub Copilot CLI",
        "sessions": "~/.copilot",
        "globs": ("otel/**/*.jsonl", "session-state/**/events.jsonl"),
        "usage_paths": (("usage",), ("data", "usage"), ("payload", "usage")),
        "aliases": {
            "input": ("prompt_tokens", "input_tokens", "input_other"),
            "output": ("completion_tokens", "output_tokens", "output"),
            "cache_read": ("cache_read_input_tokens", "cached_tokens", "input_cache_read"),
            "cache_write": ("cache_creation_input_tokens", "cache_write_tokens"),
        },
        "skills": ("~/.copilot/skills",),
        "native_skill_dir": ".copilot/skills",
    },
    "opencode": {
        "label": "OpenCode",
        "sessions": "~/.local/share/opencode",
        "globs": ("storage/message/**/*.json",),
        "usage_paths": (("tokens",), ("usage",)),
        "aliases": {
            "input": ("input", "input_tokens"),
            "output": ("output", "output_tokens"),
            "cache_read": ("cache", "cache_read", "cache_read_input_tokens"),
            "cache_write": ("cacheWrite", "cache_creation_input_tokens"),
        },
        "note": "SQLite store (opencode.db) is not read; only the JSON message store is.",
        "skills": ("~/.config/opencode/skill", "~/.opencode/skills"),
        "native_skill_dir": ".opencode/skills",
    },
    "droid": {
        "label": "Factory Droid",
        "sessions": "~/.factory/sessions",
        "globs": ("*.json", "**/*.settings.json"),
        "usage_paths": (("usage",), ("metadata", "usage"), ("totals",)),
        "aliases": {
            "input": ("input_tokens", "prompt_tokens"),
            "output": ("output_tokens", "completion_tokens"),
            "cache_read": ("cache_read_input_tokens", "cached_tokens"),
            "cache_write": ("cache_creation_input_tokens",),
        },
        "skills": ("~/.factory/skills", "~/.agents/skills"),
        "native_skill_dir": ".factory/skills",
    },
    "kiro": {
        "label": "Kiro",
        "sessions": "~/.kiro/sessions/cli",
        "globs": ("*.json",),
        "usage_paths": (("usage",), ("metrics", "usage")),
        "aliases": {
            "input": ("input_tokens", "inputTokens"),
            "output": ("output_tokens", "outputTokens"),
            "cache_read": ("cacheReadInputTokens", "cache_read_input_tokens"),
            "cache_write": ("cacheWriteInputTokens", "cache_creation_input_tokens"),
        },
        "skills": ("~/.kiro/skills", "~/.agents/skills"),
        "native_skill_dir": ".kiro/skills",
    },
    "openclaw": {
        "label": "OpenClaw",
        # Modern installs keep per-agent SQLite stores; the JSONL sessions are
        # legacy migration input. Both are declared so either is picked up.
        "sessions": "~/.openclaw",
        "globs": ("agents/*/sessions/**/*.jsonl", "**/sessions/*.jsonl"),
        "sqlite": {"path": "~/.openclaw", "glob": "**/*.db",
                   "table": "sessions",
                   "columns": {"input": ("input_tokens", "prompt_tokens"),
                               "output": ("output_tokens", "completion_tokens"),
                               "cache_read": ("cache_read_tokens", "cached_tokens"),
                               "cache_write": ("cache_write_tokens",)},
                   "summed": True},
        "usage_paths": (("message", "usage"), ("usage",)),
        "aliases": {
            "input": ("input", "input_tokens", "prompt_tokens"),
            "output": ("output", "output_tokens", "completion_tokens"),
            "cache_read": ("cacheRead", "cache_read_input_tokens", "cached_tokens"),
            "cache_write": ("cacheWrite", "cache_creation_input_tokens"),
        },
        "legacy_homes": ("~/.clawdbot", "~/.moltbot", "~/.moldbot"),
        "skills": ("~/.openclaw/skills", "~/.agents/skills"),
        "native_skill_dir": ".openclaw/skills",
    },
    "hermes": {
        "label": "Hermes Agent",
        "sessions": "~/.hermes",
        "globs": ("sessions/**/*.jsonl",),  # legacy only; state.db is canonical
        "sqlite": {"path": "~/.hermes", "glob": "state.db",
                   "table": "sessions",
                   "columns": {"input": ("input_tokens", "prompt_tokens"),
                               "output": ("output_tokens", "completion_tokens"),
                               "cache_read": ("cache_read_tokens", "cached_tokens"),
                               "cache_write": ("cache_write_tokens",)},
                   "summed": True,
                   # Hermes stores session totals, not per-message counts.
                   "per_session": True},
        "usage_paths": (("usage",), ("token_usage",), ("tokens",)),
        "aliases": {
            "input": ("input_tokens", "prompt_tokens", "input"),
            "output": ("output_tokens", "completion_tokens", "output"),
            "cache_read": ("cache_read_tokens", "cacheRead", "cache_read_input_tokens"),
            "cache_write": ("cache_write_tokens", "cacheWrite"),
        },
        "note": "state.db is canonical; legacy JSONL is read when present. Hermes mirrors the shared skill library.",
        "skills": ("~/.hermes/skills", "~/.agents/skills"),
        "native_skill_dir": ".hermes/skills",
    },
    "crush": {
        "label": "Crush",
        "sessions": "~/.local/share/crush",
        "globs": ("projects.json",),
        "usage_paths": (("usage",), ("totals",), ("cumulative",)),
        "aliases": {
            "input": ("prompt_tokens", "input_tokens"),
            "output": ("completion_tokens", "output_tokens"),
            "cache_read": ("cache_read_tokens", "cache_read_input_tokens"),
            "cache_write": ("cache_write_tokens",),
        },
        "skills": ("~/.local/share/crush/skills", "~/.agents/skills"),
        "native_skill_dir": ".crush/skills",
    },
    "aider": {
        "label": "Aider",
        "sessions": "~/.aider",
        "globs": ("**/*.jsonl", "**/*.json"),
        "usage_paths": (("usage",), ("tokens",), ("messages",)),
        "aliases": {
            "input": ("prompt_tokens", "input_tokens"),
            "output": ("completion_tokens", "output_tokens"),
            "cache_read": ("cache_read_tokens",),
            "cache_write": ("cache_write_tokens",),
        },
        "note": "Usage lives only when --analytics-log is enabled; nothing is sent anywhere.",
        "skills": ("~/.aider/skills", "~/.agents/skills"),
        "native_skill_dir": ".aider/skills",
    },
    "workbuddy": {
        "label": "WorkBuddy",
        "sessions": None,  # no token telemetry is persisted to disk
        "globs": (),
        "usage_paths": (),
        "aliases": {},
        "skills": ("~/.workbuddy/skills", "~/.workbuddy/plugins/cache"),
        "native_skill_dir": ".workbuddy/skills",
    },
}

# How much of a skill's cost is a cache hit; cache reads are far cheaper than
# fresh input, so a single blended rate would overstate or understate.
PRICE_HINT = {
    "fresh_input": "highest cost tier",
    "cache_read": "much cheaper than fresh input",
    "output": "highest per-token tier",
}


def _dig(obj: Any, path: tuple[str, ...]) -> dict[str, Any] | None:
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj if isinstance(obj, dict) else None


def _int(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _read_sqlite_usage(
    spec: dict[str, Any], root: Path, cutoff: float | None
) -> tuple[dict[str, int], int, str]:
    """Read token totals from a host's SQLite store.

    Python's `sqlite3` is in the standard library, so this adds no dependency —
    which matters because the whole tool is built on zero third-party packages.
    Databases are opened read-only via URI, and an unreadable or absent database
    yields a stated reason rather than a zero.
    """
    import sqlite3

    conf = spec.get("sqlite")
    if not conf:
        return {k: 0 for k in TOKEN_FIELDS}, 0, ""

    base = (root / str(conf["path"]).lstrip("~/")).expanduser()
    if not base.is_dir():
        return {k: 0 for k in TOKEN_FIELDS}, 0, "sqlite directory not found"

    targets: list[Path] = []
    for pattern in [conf.get("glob", "*.db")] if isinstance(conf.get("glob"), str) else (conf.get("glob") or ("*.db",)):
        targets.extend(base.glob(pattern))

    totals = {k: 0 for k in TOKEN_FIELDS}
    rows_read = 0
    last_error = ""
    for db in targets:
        try:
            if not db.is_file() or (cutoff and db.stat().st_mtime < cutoff):
                continue
        except OSError:
            continue
        try:
            uri = f"file:{db.as_posix()}?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=2) as conn:
                conn.row_factory = sqlite3.Row
                table = conf.get("table", "sessions")
                # The table may not exist yet (a host that has never run).
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
                    (table,),
                ).fetchone()
                if not exists:
                    last_error = f"{db.name} has no '{table}' table yet"
                    continue
                present = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                if not present:
                    continue
                select_cols = {"input": None, "output": None, "cache_read": None, "cache_write": None}
                for bucket, names in (conf.get("columns") or {}).items():
                    for name in names:
                        if name in present:
                            select_cols[bucket] = name
                            break
                chosen = [c for c in select_cols.values() if c]
                if not chosen:
                    last_error = f"{db.name}:{table} exposes none of the expected token columns"
                    continue
                sql = f"SELECT {', '.join(sorted(set(chosen)))} FROM {table}"
                for row in conn.execute(sql):
                    rows_read += 1
                    for bucket, col in select_cols.items():
                        if col:
                            totals[bucket] += _int(row[col])
        except Exception as e:  # noqa: BLE001 - sqlite raises many types
            last_error = f"{db.name}: {type(e).__name__}"
            continue
    return totals, rows_read, last_error


def _sum_aliases(usage: dict[str, Any], aliases: dict[str, tuple[str, ...]]) -> dict[str, int]:
    """Map a host's field names onto our canonical buckets."""
    out = {k: 0 for k in TOKEN_FIELDS}
    for bucket, names in aliases.items():
        for name in names:
            if name in usage:
                value = usage[name]
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    out[bucket] += int(value)
                break
    return out


def _host_files(spec: dict[str, Any], root: Path, cutoff: float | None) -> list[Path]:
    if not spec.get("sessions"):
        return []
    base = (root / str(spec["sessions"]).lstrip("~/")).expanduser()
    if not base.is_dir():
        return []
    found: list[Path] = []
    seen: set[str] = set()
    for pattern in spec.get("globs", ()):  # a host may need several layouts
        for path in base.glob(pattern):
            key = str(path)
            if key in seen:
                continue
            try:
                if not path.is_file() or (cutoff and path.stat().st_mtime < cutoff):
                    continue
            except OSError:
                continue
            seen.add(key)
            found.append(path)
    return found


def collect_host_usage(
    base: Path | None = None,
    since_days: float | None = None,
    hosts: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Read real token usage from every host that persists it.

    Every host returns the same keys so a consumer never branches on shape. A
    host with no telemetry — or with files whose format we do not recognise — is
    reported `unavailable`, never `0`. A confident zero is a lie with extra
    steps, and this project exists to avoid exactly that.
    """
    root = base or Path.home()
    cutoff = (time.time() - since_days * 86400) if since_days else None
    wanted = hosts or tuple(TELEMETRY_HOSTS)
    out: dict[str, Any] = {}

    for host in wanted:
        spec = TELEMETRY_HOSTS.get(host)
        if spec is None:
            out[host] = {
                "available": False, "label": host, "sessions_scanned": 0,
                "messages_with_usage": 0, "input_tokens": UNAVAILABLE,
                "output_tokens": UNAVAILABLE, "cache_read_tokens": UNAVAILABLE,
                "cache_write_tokens": UNAVAILABLE,
                "total_tokens_including_cache_read": UNAVAILABLE,
                "billable_tokens_excluding_cache_read": UNAVAILABLE,
                "provenance": UNAVAILABLE,
                "reason": f"unknown host {host!r}; known: {', '.join(sorted(TELEMETRY_HOSTS))}",
                "price_note": PRICE_HINT,
            }
            continue

        aliases = spec.get("aliases") or {}
        hints = _usage_prefilter(spec)
        totals = {k: 0 for k in TOKEN_FIELDS}
        messages = 0
        files = _host_files(spec, root, cutoff)

        if spec.get("sessions") and not files:
            reason = "session directory not found on this machine"
        elif not spec.get("sessions"):
            reason = "this host does not persist token usage to disk; read it from its own UI"
        else:
            reason = ""

        for path in files:
            try:
                handle = path.open("r", encoding="utf-8", errors="replace")
            except OSError:
                continue
            with handle:
                for line in handle:
                    # Cheap prefilter, derived from this host's own declaration
                    # so a newly added alias cannot be skipped before parsing.
                    if not any(k in line for k in hints):
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(record, list):  # some tools emit an array per file
                        items: list[Any] = record
                    else:
                        items = [record]
                    for item in items:
                        usage = None
                        for path_tuple in spec.get("usage_paths", ()):
                            usage = _dig(item, path_tuple)
                            if usage is not None:
                                break
                        if not usage:
                            continue
                        # Some hosts bury cache hits in a nested detail object.
                        # Look inside the usage block *and* at the record root,
                        # since Codex puts input_token_details beside usage
                        # rather than inside it. Only synthesize when non-zero —
                        # otherwise this would overwrite a real logged value.
                        detail = None
                        if isinstance(usage.get("input_token_details"), dict):
                            detail = usage["input_token_details"]
                        else:
                            nested = _dig(item, tuple(spec.get("cache_read_from", ())))
                            detail = nested if isinstance(nested, dict) else None
                        if detail and _int(detail.get("cached_tokens")):
                            usage = {**usage, "cache_read_input_tokens": _int(detail.get("cached_tokens"))}
                        counts = _sum_aliases(usage, aliases)
                        if not any(counts.values()):
                            continue
                        for key in TOKEN_FIELDS:
                            totals[key] += counts[key]
                        messages += 1
            # A JSON-array file is processed line-by-line above; that is harmless
            # because a pretty-printed array simply fails to parse per line.

        # Hosts whose canonical store is SQLite contribute here. Their JSONL may
        # be legacy and empty, so this is not optional for them.
        sqlite_note = ""
        if spec.get("sqlite"):
            sq_totals, sq_rows, sqlite_note = _read_sqlite_usage(spec, root, cutoff)
            if sq_rows:
                for key in TOKEN_FIELDS:
                    totals[key] += sq_totals[key]
                messages += sq_rows

        measurable = messages > 0
        billable = totals["input"] + totals["output"] + totals["cache_write"]
        record_out = {
            "available": measurable,
            "label": spec["label"],
            "sessions_scanned": len(files),
            "messages_with_usage": messages,
            "input_tokens": totals["input"] if measurable else UNAVAILABLE,
            "output_tokens": totals["output"] if measurable else UNAVAILABLE,
            "cache_read_tokens": totals["cache_read"] if measurable else UNAVAILABLE,
            "cache_write_tokens": totals["cache_write"] if measurable else UNAVAILABLE,
            "total_tokens_including_cache_read": (billable + totals["cache_read"]) if measurable else UNAVAILABLE,
            "billable_tokens_excluding_cache_read": billable if measurable else UNAVAILABLE,
            "provenance": "read directly from host session files" if measurable else UNAVAILABLE,
            "reason": "" if measurable else (
                sqlite_note or reason or
                "session files found but none contained a usage block this adapter recognises; "
                "the format may have changed"
            ),
            "sqlite_note": sqlite_note,
            "price_note": PRICE_HINT,
        }
        if spec.get("note"):
            record_out["note"] = spec["note"]
        out[host] = record_out
    return out


def host_skill_roots(hosts: tuple[str, ...] | None = None) -> list[Path]:
    """Skill directories belonging to each supported host, deduplicated."""
    roots: list[Path] = []
    for host in hosts or tuple(TELEMETRY_HOSTS):
        spec = TELEMETRY_HOSTS.get(host)
        if not spec:
            continue
        for raw in spec.get("skills", ()):
            roots.append((Path.home() / str(raw).lstrip("~/")).expanduser())
    return list(dict.fromkeys(roots))


def list_hosts() -> list[dict[str, Any]]:
    """Host capability summary, so a butler can say what it can and cannot see."""
    return [
        {
            "id": host,
            "label": spec["label"],
            "telemetry": bool(spec.get("sessions")),
            "skill_dir": spec.get("native_skill_dir", ""),
        }
        for host, spec in sorted(TELEMETRY_HOSTS.items())
    ]


# --- Library audit: breakage, staleness, redundancy --------------------------

# Repairs are deliberately conservative: fix what is provably wrong, never
# delete. Losing a user's skill to a bot's housekeeping is unforgivable; a
# rewritten frontmatter that lints cleanly is recoverable and auditable.
REPAIRABLE = ("missing_frontmatter", "description_too_long", "allowed_tools_list")


def _read_safe(path: Path) -> str | None:
    """Read a file as text with line endings normalised to '\\n'.

    Python's text mode already translates CRLF, which makes every comparison
    CRLF-safe — but it also *erases the evidence* of which convention the file
    used. Repairs need that evidence to write the file back the way it was
    found, so it is captured separately via `_uses_crlf`.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _uses_crlf(path: Path) -> bool:
    """Whether the file on disk actually uses CRLF, regardless of translation."""
    try:
        with path.open("rb") as handle:
            return b"\r\n" in handle.read(65536)
    except OSError:
        return False


def declared_skill_name(path: Path) -> str | None:
    """Best-effort read of the `name:` field without a full YAML parse.

    Used for identity only. Falls back to the folder name when the frontmatter
    is unreadable, so a broken skill is still auditable.
    """
    text = _read_safe(path)
    if not text:
        return None
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:101]:
        if line.strip() == "---":
            break
        stripped = line.strip()
        if stripped.startswith("name:"):
            value = stripped.split(":", 1)[1].strip().strip("\"'")
            return value or None
    return None


def diagnose_skill(path: Path) -> dict[str, Any]:
    """Classify one SKILL.md. Returns the failure kind plus whether it is safe to repair."""
    text = _read_safe(path)
    if text is None:
        return {"kind": "unreadable", "repairable": False, "detail": "file could not be read"}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {
            "kind": "missing_frontmatter",
            "repairable": True,
            "detail": "no opening '---' fence; the skill is invisible to any spec-compliant loader",
        }
    end = next((i for i, line in enumerate(lines[1:101], start=1) if line.strip() == "---"), -1)
    if end < 0:
        return {"kind": "unclosed_frontmatter", "repairable": False, "detail": "no closing fence in first 100 lines"}

    raw = "\n".join(lines[1:end])
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        yaml = None

    if yaml is not None:
        try:
            parsed = yaml.safe_load(raw)
        except Exception as e:  # noqa: BLE001 - yaml raises many types
            detail = f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"
            # A block sequence under `allowed-tools` is valid YAML but the wrong
            # shape for this field. Recognise it, so it gets repaired instead of
            # being lumped in with genuinely corrupt documents.
            # `[ \t]*\r?$` matters: under re.M, `$` matches before "\n" but the
            # "\r" of a CRLF pair would otherwise defeat the match.
            if isinstance(raw, str) and re.search(r"^allowed-tools:[ \t]*(?:#[^\r\n]*)?\r?$", raw, re.M):
                block = re.search(r"^allowed-tools:[ \t]*(?:#[^\r\n]*)?\r?\n((?:[ \t]+-[ \t]*.+\r?\n?)+)", raw, re.M)
                if block:
                    return {"kind": "allowed_tools_list", "repairable": True, "detail": detail}
            return {"kind": "invalid_yaml", "repairable": True, "detail": detail}
        if not isinstance(parsed, dict):
            return {"kind": "invalid_yaml", "repairable": True, "detail": "frontmatter is not a mapping"}
        description = parsed.get("description")
        if isinstance(description, str) and len(description) > 1024:
            return {
                "kind": "description_too_long",
                "repairable": True,
                "detail": f"description is {len(description)} chars; the spec limit is 1024",
            }
        allowed = parsed.get("allowed-tools")
        if isinstance(allowed, list):
            return {
                "kind": "allowed_tools_list",
                "repairable": True,
                "detail": "allowed-tools is a YAML list; the spec defines a space-separated string",
            }
        return {"kind": "ok", "repairable": False, "detail": ""}

    # Zero-dependency fallback. PyYAML may be absent (the project ships no
    # third-party packages, and CI verifies that), so the checks here are
    # textual. They must still detect the same repairable conditions, or a
    # skill would silently pass on Linux CI and fail on a dev machine with
    # PyYAML installed. Both paths must agree.
    front_text = "\n".join(lines[1:end])
    block = re.search(r"^allowed-tools:[ \t]*(?:#[^\r\n]*)?$", front_text, re.M)
    if block and re.search(r"^[ \t]+-[ \t]*\S", front_text, re.M):
        return {
            "kind": "allowed_tools_list",
            "repairable": True,
            "detail": "allowed-tools is a list; the spec defines a space-separated string",
        }
    for index, line in enumerate(lines[1:end], start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[0].isspace():
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            if key.strip() == "description":
                # Block scalars (| / >) fold to a long line; count their extent.
                measured = len(value.strip().strip("\"'"))
                if measured <= 1024 and value.strip()[:1] in ("|", ">"):
                    j = index
                    while j < len(lines) and (not lines[j].strip() or lines[j][:1].isspace()):
                        measured += len(lines[j].strip())
                        j += 1
                if measured > 1024:
                    return {
                        "kind": "description_too_long",
                        "repairable": True,
                        "detail": f"description is {measured} chars; the spec limit is 1024",
                    }
        else:
            return {
                "kind": "invalid_yaml",
                "repairable": False,
                "detail": f"line {index} is neither a comment nor a 'key: value' pair",
            }
    return {"kind": "ok", "repairable": False, "detail": ""}


def _fence_index(lines: list[str]) -> tuple[int, int]:
    """Locate the frontmatter body and everything after the closing fence."""
    if not lines or lines[0].strip() != "---":
        return -1, -1
    end = next((i for i, line in enumerate(lines[1:201], start=1) if line.strip() == "---"), -1)
    return end, (end + 1 if end > 0 else -1)


def _truncate_description_textually(
    path: Path, front: list[str], body: list[str], original_text: str
) -> tuple[bool, str]:
    """Cut an over-long description without a YAML library.

    The project ships zero third-party packages and CI proves it, so every
    repair has to work with the standard library alone. This replaces only the
    description field, in place, leaving every other key byte-identical.
    """
    crlf = _uses_crlf(path)
    out: list[str] = []
    index = 0
    total = 0
    truncated_from = 0
    while index < len(front):
        line = front[index]
        stripped = line.strip()
        if stripped.startswith("description:") and not line[:1].isspace():
            value = stripped.split(":", 1)[1].strip()
            indent = line[: len(line) - len(line.lstrip())]
            if value[:1] in ("|", ">"):
                # Folded block: consume the indented continuation lines.
                j = index + 1
                block = [value]
                while j < len(front) and (not front[j].strip() or front[j][:1].isspace()):
                    block.append(front[j].strip())
                    j += 1
                joined = " ".join(p for p in block if p).strip()
                truncated_from = len(joined)
                out.append(f"{indent}description: {joined[:1000].rstrip()}…")
                index = j
                continue
            plain = value.strip("\"'")
            truncated_from = len(plain)
            out.append(f"{indent}description: {plain[:1000].rstrip()}…")
            index += 1
            continue
        out.append(line)
        index += 1
        total += len(line)

    document = "---\n" + "\n".join(out) + "\n---\n"
    if any(b.strip() for b in body):
        document += "\n" + "\n".join(body).rstrip() + "\n"
    path.write_text(
        document.replace("\n", "\r\n") if crlf else document, encoding="utf-8", newline=""
    )
    return True, f"truncated description from {truncated_from} to 1000 chars"


def _repair_allowed_tools_textually(path: Path, front: list[str], body: list[str], text: str) -> tuple[bool, str]:
    """Flatten a list-style allowed-tools into the spec's space-separated string."""
    crlf = _uses_crlf(path)
    out: list[str] = []
    index = 0
    items: list[str] = []
    while index < len(front):
        line = front[index]
        stripped = line.strip()
        if stripped.startswith("allowed-tools:") and not line[:1].isspace():
            indent = line[: len(line) - len(line.lstrip())]
            inline = stripped.split(":", 1)[1].strip()
            if inline:
                out.append(f"{indent}allowed-tools: {inline.strip(chr(34) + chr(39))}")
                index += 1
                continue
            items = []
            j = index + 1
            while j < len(front) and front[j][:1].isspace():
                candidate = front[j].strip()
                if candidate.startswith("-"):
                    items.append(candidate[1:].strip().strip(chr(34) + chr(39)))
                j += 1
            if not items:
                return False, "no list items found under allowed-tools"
            out.append(f"{indent}allowed-tools: {' '.join(items)}")
            index = j
            continue
        out.append(line)
        index += 1

    document = "---\n" + "\n".join(out) + "\n---\n"
    if any(b.strip() for b in body):
        document += "\n" + "\n".join(body).rstrip() + "\n"
    path.write_text(
        document.replace("\n", "\r\n") if crlf else document, encoding="utf-8", newline=""
    )
    return True, "converted allowed-tools to the spec's space-separated string"


def repair_skill(path: Path, kind: str) -> tuple[bool, str]:
    """Apply a conservative, in-place repair. Returns (changed, note)."""
    text = _read_safe(path)
    if text is None:
        return False, "unreadable"

    if kind == "description_too_long":
        lines = text.splitlines()
        end = next((i for i, line in enumerate(lines[1:101], start=1) if line.strip() == "---"), -1)
        if end < 0:
            return False, "no closing fence"
        front = lines[1:end]
        body = lines[end + 1:]
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError:
            return _truncate_description_textually(path, front, body, text)
        parsed = yaml.safe_load("\n".join(front)) or {}
        original = str(parsed.get("description", ""))
        # Truncate on a character boundary and state plainly that it was cut.
        parsed["description"] = original[:1000].rstrip() + "…"
        updated = (
            "---\n"
            + yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip()
            + "\n---"
            + ("\n" + "\n".join(body) if any(b.strip() for b in body) else "\n")
        )
        path.write_text(updated, encoding="utf-8")
        return True, f"truncated description from {len(original)} to 1000 chars"

    if kind == "allowed_tools_list":
        # Windows checkouts are frequently CRLF; a regex written against bare
        # \n silently fails to match, which looks like "repair did nothing".
        crlf = _uses_crlf(path)
        body = text.replace("\r\n", "\n")
        fence, _ = _fence_index(body.splitlines())
        lines = body.splitlines()
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError:
            if fence < 0:
                return False, "no closing fence"
            return _repair_allowed_tools_textually(
                path, lines[1:fence], lines[fence + 1:], text
            )
        # Anchoring at the opening fence avoids the greedy list match eating
        # text that sits before it.
        start = body.find("---")
        if start < 0:
            return False, "no opening fence"
        head, _, rest = body[start:].partition("\n")
        if head.strip() != "---":
            return False, "unexpected content before the frontmatter"
        rest_lines = rest.splitlines()
        # `rest` starts *after* the opening fence, so the closing fence is at
        # whatever index carries '---'; frontmatter is everything before it.
        close = next((i for i, line in enumerate(rest_lines) if line.strip() == "---"), -1)
        if close < 0:
            return False, "no closing fence"
        front = rest_lines[:close]
        front_text = "\n".join(front)
        # Everything after the closing fence is the body, preserved verbatim.
        body_text = "\n".join(rest_lines[close + 1:])

        block = re.search(r"^allowed-tools:[ \t]*(?:#[^\r\n]*)?$", front_text, re.M)
        if block:
            items = [m.group(1).strip() for m in re.finditer(r"^[ \t]+-[ \t]*(.+?)[ \t]*$", front_text, re.M)]
            if not items:
                return False, "no list items found under allowed-tools"
            joined = " ".join(item.strip("\"'") for item in items)
            new_front = [
                f"allowed-tools: {joined}" if line.strip().startswith("allowed-tools:") else line
                for line in front
            ]
            # Drop the original list items; their content moved onto one line.
            new_front = [
                line for line in new_front
                if not re.match(r"^[ \t]+-[ \t]*", line)
            ]
            front = new_front
        else:
            # Valid YAML, wrong shape: round-trip through the parser.
            try:
                import yaml  # type: ignore[import-not-found]
            except ImportError:
                return False, "needs PyYAML to rewrite frontmatter safely"
            try:
                parsed = yaml.safe_load(front_text) or {}
            except Exception:  # noqa: BLE001
                return False, "document does not parse as YAML; repair it by hand"
            parsed["allowed-tools"] = (
                " ".join(str(x) for x in parsed["allowed-tools"])
                if isinstance(parsed.get("allowed-tools"), list)
                else str(parsed.get("allowed-tools", ""))
            )
            front = yaml.safe_dump(
                parsed, allow_unicode=True, sort_keys=False, default_flow_style=False
            ).rstrip().splitlines()

        # Rebuild as: opening fence, frontmatter, blank line, closing fence, body.
        document = "---\n" + "\n".join(front).rstrip() + "\n\n---\n"
        if body_text.strip():
            document += "\n" + body_text.rstrip() + "\n"
        path.write_text(
            document.replace("\n", "\r\n") if crlf else document,
            encoding="utf-8",
            newline="",
        )
        return True, "converted allowed-tools to the spec's space-separated string"

    if kind == "missing_frontmatter":
        # Derive a minimal, valid frontmatter from the folder name.
        name = path.parent.name
        if not NAME_RE.fullmatch(name):
            return False, f"directory name {name!r} cannot be used as a valid skill name"
        lines = text.splitlines()
        body = "\n".join(lines).lstrip()
        # Best-effort description from the first prose line, trimmed to spec.
        first = next((ln.strip("# ").strip() for ln in body.splitlines() if ln.strip()), "")
        description = (first[:200] or f"Skill {name}").replace(":", " -").replace('"', "'")
        updated = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"
        path.write_text(updated, encoding="utf-8")
        return True, f"synthesised frontmatter from directory name; description derived from the body"

    return False, f"no automatic repair for {kind}"


def audit_library(
    roots: list[Path],
    unused_days: float = 90.0,
    fix: bool = False,
    ledger: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Full-library health check: broken, stale, duplicated, and repairable."""
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    by_name: dict[str, list[str]] = {}
    counts = {"ok": 0, "broken": 0, "blocking": 0, "stale": 0, "duplicate": 0}

    for root in roots:
        root = root.expanduser()
        if not root.is_dir() or root.is_symlink():
            continue
        for skill_md in _skill_files(root):
            key = str(skill_md.resolve())
            if key in seen:
                continue
            seen.add(key)
            diagnosis = diagnose_skill(skill_md)
            # Identify by the *declared* name, not the folder. Plugin caches nest
            # as <vendor>/<plugin>/<version>/SKILL.md, so folder names look like
            # "5.8.2-wb.39298511.g37a65c0b" — counting those as skills invents
            # dozens of phantom duplicates.
            name = declared_skill_name(skill_md) or skill_md.parent.name
            by_name.setdefault(name, []).append(str(skill_md))

            record: dict[str, Any] = {
                "name": name,
                "path": str(skill_md),
                "status": diagnosis["kind"],
                "detail": diagnosis["detail"],
                "repairable": diagnosis["repairable"],
                "modified_days_ago": None,
                "stale": False,
            }
            try:
                age_days = (time.time() - skill_md.stat().st_mtime) / 86400
                record["modified_days_ago"] = round(age_days, 1)
                record["stale"] = age_days > unused_days
            except OSError:
                pass

            if diagnosis["kind"] == "ok":
                counts["ok"] += 1
            else:
                counts["broken"] += 1
                if not diagnosis["repairable"]:
                    counts["blocking"] += 1
            if record["stale"]:
                counts["stale"] += 1

            if fix and diagnosis["repairable"] and diagnosis["kind"] in REPAIRABLE:
                changed, note = repair_skill(skill_md, diagnosis["kind"])
                record["repaired"] = changed
                record["repair_note"] = note
                record["status_after"] = diagnose_skill(skill_md)["kind"]
            entries.append(record)

    duplicates = {n: paths for n, paths in by_name.items() if len(paths) > 1}
    counts["duplicate"] = len(duplicates)

    blocking = [e for e in entries if e["status"] != "ok" and not e["repairable"]]
    repairable = [e for e in entries if e["status"] != "ok" and e["repairable"]]
    stale = [e for e in entries if e["stale"]]

    recommendations: list[dict[str, str]] = []
    if repairable:
        recommendations.append({
            "action": "repair",
            "target": f"{len(repairable)} skill(s) with recoverable frontmatter problems",
            "command": "python skills/aletheia/scripts/router.py audit --fix",
            "why": "These load in some hosts and silently fail in others. Repair rewrites frontmatter only.",
        })
    if blocking:
        recommendations.append({
            "action": "manual_review",
            "target": f"{len(blocking)} skill(s) needing a human decision",
            "command": "python skills/aletheia/scripts/router.py audit --json",
            "why": "Frontmatter is malformed beyond automatic repair. Open the file and fix, or remove it deliberately.",
        })
    if stale:
        recommendations.append({
            "action": "review_stale",
            "target": f"{len(stale)} skill(s) not modified in over {unused_days:g} days",
            "command": "python skills/aletheia/scripts/router.py audit --unused-days 30",
            "why": "Stale skills still cost metadata every turn. Narrow or remove them deliberately — nothing is deleted for you.",
        })
    if duplicates:
        recommendations.append({
            "action": "review_duplicates",
            "target": f"{len(duplicates)} skill(s) installed in more than one location",
            "command": "python skills/aletheia/scripts/router.py inventory --limit 1",
            "why": "Duplicates cost metadata twice. Keep one, but choose deliberately — versions may differ.",
        })

    return {
        "scanned": len(entries),
        "counts": counts,
        "unused_days_threshold": unused_days,
        "fix_applied": fix,
        "broken": [e for e in entries if e["status"] != "ok"],
        "stale_entries": stale,
        "duplicates": duplicates,
        "recommendations": recommendations,
        "safety_note": (
            "--fix rewrites frontmatter in place and never deletes a file. Anything it cannot repair "
            "safely is reported for a human decision instead."
        ),
    }


def render_audit_text(result: dict[str, Any]) -> str:
    counts = result["counts"]
    lines = [
        "Aletheia library audit",
        f"  scanned {result['scanned']} skill(s)",
        f"  healthy {counts['ok']}   broken {counts['broken']} (blocking {counts['blocking']})"
        f"   stale {counts['stale']}   duplicated {counts['duplicate']}",
        "",
    ]
    broken = result["broken"]
    if broken:
        lines.append("Broken skills:")
        for item in broken[:20]:
            mark = "fixed" if item.get("repaired") else ("auto-fixable" if item["repairable"] else "manual")
            lines.append(f"  [{mark}] {item['name']} — {item['detail'][:90]}")
            if item.get("repair_note"):
                lines.append(f"           → {item['repair_note']}")
        if len(broken) > 20:
            lines.append(f"  … and {len(broken) - 20} more")
        lines.append("")
    if result["duplicates"]:
        lines.append("Installed more than once:")
        for name, paths in list(result["duplicates"].items())[:10]:
            lines.append(f"  {name} ×{len(paths)}")
        lines.append("")
    if result["recommendations"]:
        lines.append("Recommended next steps:")
        for rec in result["recommendations"]:
            lines.append(f"  · {rec['action']}: {rec['target']}")
            lines.append(f"      {rec['command']}")
            lines.append(f"      {rec['why']}")
    else:
        lines.append("Nothing needs attention.")
    lines.append("")
    lines.append(result["safety_note"])
    return "\n".join(lines)


def _latest_comparison(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Newest record that actually carries a scenario comparison.

    Telemetry records have none, so blindly reading `records[-1]` produced a
    headline of em-dashes even when a real comparison sat one line above it.
    """
    for rec in reversed(records):
        comparison = (rec.get("comparison") or {}).get("comparison")
        if comparison and "saved_tokens_est" in comparison:
            return comparison
    return {}


def render_report_markdown(records: list[dict[str, Any]], as_text: bool = False) -> str:
    """Readable-in-a-chat rendering of the same data as the HTML report.

    This exists because a report has three delivery tiers — URL, file, then
    plain text — and the third must still be *formatted*. Falling back to a bare
    dump of numbers would be a downgrade the reader can feel. Same data, same
    three-state labelling, laid out for reading rather than for printing.
    """
    def n(value: Any) -> str:
        if isinstance(value, int):
            return f"{value:,}"
        return str(value)

    def tag(state: str) -> str:
        if as_text:
            return f"[{state}]"
        return f"**{state}**"

    lines: list[str] = []
    add = lines.append

    add("# Aletheia routing cost report" if not as_text else "ALETHEIA ROUTING COST REPORT")
    add("")
    add(f"_Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} · {len(records)} record(s) · local ledger_")
    add("")

    # Provenance legend first, so nothing below can be misread.
    add("## How to read the numbers")
    add("")
    add("| Marking | Meaning |")
    add("| --- | --- |")
    add("| `measured` | read directly from host session files on this machine |")
    add("| `est` | estimated from measured characters via a documented bytes-per-token constant |")
    add("| `unavailable` | the host exposes no such figure; deliberately left blank |")
    add("")

    last_cmp = _latest_comparison(records)
    without_tokens = last_cmp.get("without_aletheia", {}).get("metadata_tokens_est", "—")
    with_tokens = last_cmp.get("with_aletheia_scoped", {}).get("metadata_tokens_est", "—")
    saved = last_cmp.get("saved_tokens_est")
    pct = last_cmp.get("saved_percent")

    add("## Headline")
    add("")
    add("| Metric | Value | Basis |")
    add("| --- | ---: | --- |")
    add(f"| Metadata tokens, no routing | {n(without_tokens)} | estimated |")
    add(f"| Metadata tokens, scoped | {n(with_tokens)} | estimated |")
    if isinstance(saved, int):
        add(f"| Reduction | {n(saved)} ({pct}%) | estimated |")
    add("| Actual host tokens | see per-host table below | measured where the host logs it |")
    add("")

    telemetry: dict[str, Any] = {}
    for rec in reversed(records):
        if rec.get("host_telemetry"):
            telemetry = rec["host_telemetry"]
            break
    if telemetry:
        add("## Actual host usage, read from session files")
        add("")
        add("| Host | Status | Input | Output | Cache read | Cache write | Messages |")
        add("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
        for info in telemetry.values():
            label = info.get("label", "?")
            if info.get("available"):
                add(
                    f"| {label} | {tag('measured')} | {n(info['input_tokens'])} | {n(info['output_tokens'])} |"
                    f" {n(info['cache_read_tokens'])} | {n(info['cache_write_tokens'])} |"
                    f" {n(info['messages_with_usage'])} |"
                )
            else:
                reason = info.get("reason", "")
                add(f"| {label} | {tag('unavailable')} | — | — | — | — | — |")
                if reason:
                    # Indented continuation row, so the reason stays attached to
                    # its host instead of floating as a stray line.
                    add(f"| ↳ reason | {reason} | | | | | |")
        add("")
        add("_Cache reads cost a fraction of fresh input, so they are never blended into one total._")
        add("")

    if records:
        add("## Measurements")
        add("")
        add("| Task id | Phase | Label | No routing | Scoped | Actual |")
        add("| --- | --- | --- | ---: | ---: | ---: |")
        for rec in records:
            with_a = rec.get("with_aletheia", {})
            without = rec.get("without_aletheia", {})
            actual = rec.get("actual_tokens", UNAVAILABLE)
            if "metadata_tokens_est_unscoped" in without:
                no_col = f"{n(without['metadata_tokens_est_unscoped'])} est"
                yes_col = f"{n(with_a.get('metadata_tokens_est_scoped', 0))} est"
            else:
                no_col = yes_col = "n/a"
            act_col = n(actual) if isinstance(actual, int) else "unavailable"
            add(
                f"| `{rec.get('task_id', '')}` | {rec.get('phase', '')} |"
                f" {str(rec.get('label', ''))[:40]} | {no_col} | {yes_col} | {act_col} |"
            )
        add("")

    for rec in reversed(records):
        items = rec.get("comparison", {}).get("not_quantified")
        if items:
            add("## Deliberately not quantified")
            add("")
            add("These are refused rather than estimated, because a guess would look like a result:")
            add("")
            for item in items:
                add(f"- **{item['claim']}** — `{item['value']}`")
                add(f"  {item['why']}")
            add("")
            break

    add("## Getting real numbers")
    add("")
    add("1. Run the same task twice in the host: once normally, once with a scoped allowlist.")
    add("2. Read the token usage the host itself reports at the end of each run.")
    add("3. Record it with `router.py measure \"task\" --phase after --actual-tokens <n>`.")
    add("")
    add("---")
    add("")
    add("_Ledger: `~/.aletheia/ledger.jsonl` · nothing leaves this machine · "
        "measured ≠ estimated ≠ available_")

    text = "\n".join(lines)
    if as_text:
        # Strip Markdown syntax a plain terminal or chat bubble cannot render,
        # while keeping every heading rule and all column alignment.
        out = []
        for line in text.splitlines():
            line = re.sub(r"^#+\s*", lambda m: "=" * len(m.group(0)) + " ", line)
            line = re.sub(r"^>\s*", "", line)
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)      # bold
            line = re.sub(r"`(.+?)`", r"\1", line)             # inline code
            line = line.replace("_", "")
            line = re.sub(r"^-\s+", "- ", line)
            line = re.sub(r"^\|\s*---.*$", "  " + "-" * 40, line)
            line = re.sub(r"\s*\|\s*", "  ", line)
            out.append(line.rstrip())
        text = "\n".join(out)
    return text


# --- Active measurement ------------------------------------------------------
# The passive adapters above wait for a host to volunteer its numbers. This
# section is the opposite: walk the machine, find every source that *can* be
# measured, and report what that adds up to — without asking the host anything.
#
# What this can genuinely measure:
#   * token usage, for any host whose session files record it (no host needed)
#   * bytes of skill metadata actually loaded into context
#   * bytes of the skill bodies loaded, from the SKILL.md files themselves
#   * growth of a host's own log files, which correlate with work done
#
# What it cannot, and will not fake:
#   * a host that persists no token counter (WorkBuddy) — the number exists in
#     the network response, not on disk. Reporting a guess here would be worse
#     than reporting nothing, because the guess would look like a measurement.

# Claude/OpenAI-style pricing is deliberately NOT bundled. A stale price table
# silently turns into a confidently wrong money figure, which is precisely the
# failure this project exists to prevent. Bring your own.
PRICE_TABLE_ENV = "ALETHEIA_PRICES"


def count_tokens(text: str, script: str = "cjk_mixed") -> int:
    """Estimate tokens from characters using a documented bytes-per-token rule.

    This is an ESTIMATE and is always labelled as one. It is useful for
    relative comparison (this routing decision vs that one), which is what a
    butler actually needs — not for billing.
    """
    return estimate_tokens(len(text), script)


def measure_local_context_load(
    skills: list[Skill], task: str = "", allowed: set[str] | None = None
) -> dict[str, Any]:
    """What routing costs in context, measured from the files themselves.

    Metadata is loaded for every visible skill; a skill's body is loaded only if
    selected. Both counts are character counts read from disk right now, so the
    token figure is a conversion of a measurement — not a guess.
    """
    visible, _ = apply_scope(skills, allowed)
    meta_chars = sum(len(s.name) + len(s.description) + 40 for s in visible)
    # A rough body cost: every SKILL.md in the visible set is a real file whose
    # size we can read. The agent reads only the ones it selects, so report the
    # full pool and let the caller pick a subset.
    body_pool_chars = 0
    for skill in visible:
        raw = _read_safe(Path(skill.path))
        if raw:
            body_pool_chars += len(raw)
    task_chars = len(task)
    return {
        "task_chars": task_chars,
        "task_tokens_est": count_tokens(task),
        "metadata_chars": meta_chars,
        "metadata_tokens_est": count_tokens("\0" * meta_chars),
        "skill_body_pool_chars": body_pool_chars,
        "skill_body_pool_tokens_est": count_tokens("\0" * body_pool_chars),
        "visible_skills": len(visible),
        "total_skills": len(skills),
        "basis": "characters read from disk now; tokens converted by a documented rule",
    }


def measure_host_growth(
    roots: dict[str, Path], since_hours: float = 24.0
) -> list[dict[str, Any]]:
    """Bytes written by host log directories in a time window.

    A weak but honest proxy: it says how much a host *did*, not how many tokens
    it spent. Reported separately and never summed into a token total, because
    log bytes and tokens are not the same unit.
    """
    cutoff = time.time() - since_hours * 3600
    out: list[dict[str, Any]] = []
    for host, path in roots.items():
        if not path.is_dir():
            continue
        total = 0
        files = 0
        newest = 0.0
        try:
            for item in path.rglob("*"):
                try:
                    if not item.is_file():
                        continue
                    stat = item.stat()
                except OSError:
                    continue
                if stat.st_mtime >= cutoff:
                    total += stat.st_size
                    files += 1
                    newest = max(newest, stat.st_mtime)
        except OSError:
            continue
        if files:
            out.append({
                "host": host,
                "path": str(path),
                "files_changed": files,
                "bytes_written": total,
                "since_hours": since_hours,
                "newest_mtime": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(newest)),
                "unit": "bytes of log output — NOT tokens",
                "interpretation": "proxy for work volume only; cannot be converted to tokens",
            })
    return out


def active_measurement(
    roots: list[Path] | None = None,
    since_days: float | None = 30.0,
    task: str = "",
    hosts: tuple[str, ...] | None = None,
    allowed: set[str] | None = None,
    home: Path | None = None,
) -> dict[str, Any]:
    """Measure everything measurable on this machine, without asking any host.

    The point is that measurement no longer depends on a host offering it. For
    hosts that already persist usage that is a read; for hosts that do not, the
    context load and log growth are still real numbers, and the missing piece is
    named explicitly instead of filled in.
    """
    skill_roots = roots or default_roots(Path.cwd())
    # Discover returns every install, including duplicate copies. The butler's
    # view is the de-duplicated one, otherwise a skill mirrored across four
    # agents would be counted four times in the context cost.
    skills, issues = discover(skill_roots)
    inventory = build_inventory(skills, issues, skill_roots, limit=0)
    unique_paths = [e["path"] for e in inventory["entries"]]
    by_path = {s.path: s for s in skills}
    unique_skills = [by_path[p] for p in unique_paths if p in by_path]

    # `home` lets a caller point the whole measurement at a different root —
    # without it a test can never isolate itself from the real machine.
    usage = collect_host_usage(base=home, since_days=since_days, hosts=hosts)
    measured_hosts = {h: v for h, v in usage.items() if v.get("available")}
    silent_hosts = {h: v for h, v in usage.items() if not v.get("available")}

    # Aggregate only across hosts that actually reported. Summing a set in which
    # some members are zero-by-absence would understate the total.
    token_totals = {k: 0 for k in TOKEN_FIELDS}
    # `collect_host_usage` names its fields `cache_read_tokens` while the
    # canonical bucket is `cache_read`. Reading the wrong key silently yields 0,
    # which is exactly the "confident zero" this project refuses to emit.
    key_map = {
        "input": "input_tokens",
        "output": "output_tokens",
        "cache_read": "cache_read_tokens",
        "cache_write": "cache_write_tokens",
    }
    for info in measured_hosts.values():
        for key in TOKEN_FIELDS:
            token_totals[key] += _int(info.get(key_map[key]))

    home = home or Path.home()
    log_roots = {
        "workbuddy": home / ".workbuddy" / "logs",
        "codebuddy": home / ".codebuddy" / "logs",
        "claude": home / ".claude" / "projects",
        "codex": home / ".codex" / "sessions",
    }

    return {
        "measured_without_asking_any_host": True,
        "token_totals": {
            **token_totals,
            "hosts_included": sorted(measured_hosts),
            "hosts_excluded_no_telemetry": sorted(silent_hosts),
            "completeness": (
                "complete across this machine" if not silent_hosts
                else f"partial — {len(silent_hosts)} host(s) persist no token counter"
            ),
        },
        "context_load": measure_local_context_load(unique_skills, task, allowed),
        "inventory": {
            "unique_skills": len(unique_skills),
            "install_locations": len(skills),
            "duplicate_installs": len(skills) - len(unique_skills),
            "note": "context cost is counted once per unique skill, not per install",
        },
        "log_growth": measure_host_growth(log_roots),
        "unmeasurable_here": {
            "host_internal_reasoning_tokens": UNAVAILABLE,
            "why": (
                "Some hosts do not log reasoning tokens at all, and none of them log "
                "them to disk. No amount of local inspection recovers a number that was "
                "never written down. Read it from the host's own accounting."
            ),
            "billed_cost": UNAVAILABLE,
            "billed_cost_why": (
                "Requires a model id and a price table. " + PRICE_TABLE_ENV +
                " can supply prices, but the model id must come from the host."
            ),
        },
        "honesty": (
            "Everything above was read from disk. Token figures from hosts that log them "
            "are measured; context figures are conversions of measured characters; log "
            "figures are bytes and are not tokens. Nothing here is invented."
        ),
    }


def fail(message: str, code: int = 2) -> int:
    """Report a business-logic failure in the one protocol this CLI has.

    Everything here speaks JSON on stdout with a non-zero exit, so a consumer
    parses one shape. `parser.error` was previously mixed in for the same class
    of failure, which meant a caller had to handle both stderr text and JSON —
    and machine callers generally only handle one.

    Argparse still owns genuine argument-parsing errors (unknown subcommand,
    missing required value): those happen before any command semantics exist,
    and its usage message is the right answer there.
    """
    print(json.dumps({"error": message}, ensure_ascii=False, indent=2))
    return code


# --- Update detection -------------------------------------------------------
# Detection only. It reports what is out there and stops there.
#
# Updating a skill that another agent is currently reading is a bad trade: the
# reader gets a half-written file, and the user did not ask for that risk. So
# there is deliberately no `--apply` here. The command tells you what changed
# and where; the update itself stays a human decision, the same way every other
# destructive action in this project does.

UPDATE_REPO = "https://github.com/Xiranwuxianxi/aletheia"


def _git(repo: Path, *args: str, timeout: int = 12) -> tuple[int, str]:
    """Run a read-only git command. Never raises; returns (code, output)."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=timeout,
            errors="replace",
        )
    except FileNotFoundError:
        return 127, "git not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, f"git timed out after {timeout}s"
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"
    return proc.returncode, (proc.stdout or proc.stderr or "").strip()


def _repo_root(start: Path | None = None) -> Path | None:
    """Find the repository this skill lives in, if it is inside one."""
    here = (start or Path(__file__).resolve()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _parse_version(text: str) -> tuple[int, ...]:
    match = re.search(r"v?(\d+(?:\.\d+)*)", text)
    return tuple(int(p) for p in match.group(1).split(".")) if match else ()


def _fetch_remote_tags(repo: Path) -> tuple[dict[str, str], str]:
    """Read remote tags via `git ls-remote`. Returns (tag->commit, error)."""
    code, out = _git(repo, "ls-remote", "--tags", "origin")
    if code != 0:
        return {}, out or f"git ls-remote failed ({code})"
    tags: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        name = ref.rsplit("/", 1)[-1]
        if name.endswith("^{}"):       # annotated tag points here
            name = name[:-3]
        tags[name] = sha
    return tags, ""


def check_update(
    repo: Path | None = None, fetch: bool = True
) -> dict[str, Any]:
    """Compare this checkout against its remote. Reports; never modifies."""
    root = repo or _repo_root()
    # An explicit path must actually be a repository root. Without this check a
    # directory inside some unrelated repo passes every git call, because git
    # walks upward looking for .git.
    if root is None or not (root / ".git").exists():
        return {
            "checked": False,
            "reason": "this skill copy is not inside a git repository, so there is no "
                      "upstream to compare against",
            "local_version": VERSION,
            "latest_version": UNAVAILABLE,
            "update_available": UNAVAILABLE,
        }

    result: dict[str, Any] = {"checked": True, "repo": str(root), "local_version": VERSION}

    code, remote = _git(root, "remote", "get-url", "origin")
    result["remote"] = remote if code == 0 else UNAVAILABLE
    if code != 0:
        result["reason"] = "no git remote named origin"

    code, head = _git(root, "rev-parse", "--short", "HEAD")
    result["local_commit"] = head if code == 0 else UNAVAILABLE
    code, branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    result["branch"] = branch if code == 0 else UNAVAILABLE

    # Which tag is this checkout sitting on, if any?
    code, describe = _git(root, "describe", "--tags", "--abbrev=0")
    result["local_tag"] = describe if code == 0 else UNAVAILABLE
    code, dirty = _git(root, "status", "--porcelain")
    result["uncommitted_changes"] = len([l for l in dirty.splitlines() if l.strip()]) if code == 0 else None

    if not fetch:
        result["latest_tag"] = UNAVAILABLE
        result["latest_version"] = UNAVAILABLE
        result["update_available"] = UNAVAILABLE
        result["reason"] = "remote not contacted (--no-fetch)"
        return result

    tags, error = _fetch_remote_tags(root)
    if error:
        # No network, auth failure, or a repo without tags. Say which.
        result["latest_tag"] = UNAVAILABLE
        result["latest_version"] = UNAVAILABLE
        result["update_available"] = UNAVAILABLE
        result["reason"] = f"could not read remote tags: {error}"
        return result

    if not tags:
        result["latest_tag"] = UNAVAILABLE
        result["latest_version"] = UNAVAILABLE
        result["update_available"] = UNAVAILABLE
        result["reason"] = "the remote has no tags yet, so there is no version to compare against"
        result["remote_tag_count"] = 0
        return result

    def sort_key(name: str) -> tuple[int, ...]:
        return _parse_version(name)

    ordered = sorted(tags, key=sort_key)
    latest = ordered[-1]
    result["latest_tag"] = latest
    result["latest_version"] = sort_key(latest)
    result["remote_tag_count"] = len(ordered)
    result["available_tags"] = ordered[-6:]

    local_v = _parse_version(result.get("local_tag") or "") or _parse_version(VERSION)
    latest_v = result["latest_version"]
    result["update_available"] = bool(latest_v > local_v)

    if result["update_available"]:
        code, log = _git(root, "log", "--oneline", f"HEAD..{tags[latest]}", timeout=8)
        result["commits_behind"] = len([l for l in log.splitlines() if l.strip()]) if code == 0 else UNAVAILABLE
        result["commits_preview"] = [l for l in log.splitlines() if l.strip()][:10] or UNAVAILABLE
    else:
        result["commits_behind"] = 0
        result["commits_preview"] = []

    result["how_to_update"] = [
        f"cd {root}",
        "git fetch origin",
        f"git log HEAD..origin/{result.get('branch', 'main')} --oneline   # read what changed",
        "git pull --ff-only origin " + str(result.get("branch") or "main"),
        "python -m unittest discover -s tests    # verify before trusting it",
    ]
    result["safety"] = (
        "Aletheia never runs this for you. A skill file being read by another agent "
        "while it is rewritten is a bad trade, so updating stays your decision."
    )
    return result


# --- Where is this skill installed? -------------------------------------------

def find_installations(name: str = "aletheia") -> dict[str, list[str]]:
    """Every host directory this skill is installed into.

    A skill can live in several places at once — that is normal, not a problem.
    Knowing where is what makes an update actionable instead of vague.
    """
    found: dict[str, list[str]] = {}
    for host, spec in TELEMETRY_HOSTS.items():
        for raw in spec.get("skills", ()):
            root = Path(raw).expanduser()
            if not root.is_dir():
                continue
            candidate = root / name
            if (candidate / "SKILL.md").is_file():
                found.setdefault(spec["label"], []).append(str(candidate))
    # The repository working copy counts too: it is the source, not an install.
    repo = _repo_root()
    if repo and (repo / "skills" / name / "SKILL.md").is_file():
        found.setdefault("(this repository)", []).append(str(repo / "skills" / name))
    return found


def scan_upstreams(
    roots: list[Path] | None = None, since_days: float = 365.0
) -> dict[str, Any]:
    """Find every installed skill and what can be known about its origin.

    Most third-party skills carry no upstream URL, and inventing one would be
    worse than reporting nothing. Where the evidence is absent, this says so.
    """
    skill_roots = roots or default_roots(Path.cwd())
    skills, issues = discover(skill_roots)
    inventory = build_inventory(skills, issues, skill_roots, limit=0)
    by_path = {s.path: s for s in skills}
    unique = [by_path[e["path"]] for e in inventory["entries"] if e["path"] in by_path]

    cutoff = time.time() - since_days * 86400
    rows: list[dict[str, Any]] = []
    untracked = 0
    for skill in unique:
        path = Path(skill.path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        # A skill inside some other git repository has a reachable upstream.
        repo = _repo_root(path.parent)
        rows.append({
            "name": skill.name,
            "path": skill.path,
            "in_git_repo": repo is not None,
            "upstream": str(repo) if repo else UNAVAILABLE,
            "upstream_reason": "" if repo else "not inside a git repository; no upstream recorded",
            "days_since_modified": round((time.time() - mtime) / 86400, 1) if mtime else UNAVAILABLE,
            "stale_over_days": round((time.time() - mtime) / 86400, 1) > since_days if mtime else UNAVAILABLE,
        })
        if repo is None:
            untracked += 1

    self_check = check_update()
    return {
        "total_unique_skills": len(unique),
        "install_locations": len(skills),
        "tracked_by_git": len(unique) - untracked,
        "no_upstream_recorded": untracked,
        "note": (
            "A skill is only refreshable if something records where it came from. "
            "Those that are not inside a repository have no upstream this tool can "
            "name — inventing one would be worse than reporting the gap."
        ),
        "self": self_check,
        "installations": find_installations(),
        "skills": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only, local Agent Skills discovery & routing hints")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "route", "lint"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", action="append", default=[], help="skill parent directory, repeatable; no root means conventional local paths")
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

    meas = sub.add_parser("measure", help="record what a routing step actually costs (local ledger, no network)")
    meas.add_argument("task", help="the task text about to be routed")
    meas.add_argument("--root", action="append", default=[])
    meas.add_argument("--only", action="append", default=[], help="allowlist for the scoped scenario")
    meas.add_argument("--phase", choices=("before", "after"), default="before", help="before = estimate baseline, after = record result")
    meas.add_argument("--task-id", default=None, help="group before/after records; generated if omitted")
    meas.add_argument("--label", default=None, help="what this measurement represents, e.g. 'deck-task'")
    meas.add_argument("--actual-tokens", type=int, default=None, help="ONLY a number you read from the host; never invented")
    meas.add_argument("--note", default=None, help="free-text note stored with the record")
    meas.add_argument("--ledger", type=Path, default=None, help="override ledger location")

    rep = sub.add_parser("report", help="summarize the local ledger as HTML, markdown, or text")
    rep.add_argument("--ledger", type=Path, default=None, help="ledger file to read")
    rep.add_argument("--out", type=Path, default=None, help="write the report here (extension picks the format)")
    rep.add_argument("--format", choices=("html", "md", "text"), default=None,
                     help="html = self-contained page; md/text = readable in a chat or terminal")
    rep.add_argument("--json", action="store_true", help="print the raw summary JSON")

    tel = sub.add_parser("telemetry", help="read real token usage from hosts that persist it")
    tel.add_argument("--since-days", type=float, default=None, help="only sessions modified within N days")
    tel.add_argument("--host", action="append", default=[], help="restrict to a host id, or 'all'; omit for every known host")
    tel.add_argument("--record", type=Path, default=None, help="append this measurement to the ledger")
    tel.add_argument("--ledger", type=Path, default=None, help="override ledger location")

    hosts_cmd = sub.add_parser("hosts", help="list every supported agent host and what can be read from it")
    hosts_cmd.add_argument("--json", action="store_true", help="machine-readable output (default)")

    est_cmd = sub.add_parser(
        "estimate",
        help="measure token usage by walking this machine, without asking any host",
    )
    est_cmd.add_argument("--root", action="append", default=[], help="extra skill root (repeatable)")
    est_cmd.add_argument("--task", default="", help="the task text, to size the context load")
    est_cmd.add_argument("--only", action="append", default=[],
                         help="allowlist, to see the scoped cost instead of the whole library")
    est_cmd.add_argument("--host", action="append", default=[], help="restrict to a host id, or 'all'")
    est_cmd.add_argument("--since-days", type=float, default=30.0, help="usage window in days")
    est_cmd.add_argument("--record", type=Path, default=None, help="append this measurement to the ledger")
    est_cmd.add_argument("--ledger", type=Path, default=None, help="override ledger location")

    upd = sub.add_parser(
        "update",
        help="check whether this skill or any installed skill has a newer version (detection only)",
    )
    upd.add_argument("--no-fetch", action="store_true",
                     help="report local state without contacting the remote")
    upd.add_argument("--repo", type=Path, default=None, help="repository to check (default: this skill's repo)")
    upd.add_argument("--scan", action="store_true",
                     help="also report every installed skill and whether an upstream is known")
    upd.add_argument("--unused-days", type=float, default=365.0, help="staleness threshold for --scan")

    aud = sub.add_parser("audit", help="inspect the whole library for breakage, staleness and redundancy")
    aud.add_argument("--root", action="append", default=[])
    aud.add_argument("--unused-days", type=float, default=90.0, help="a skill unseen for this long is flagged stale")
    aud.add_argument("--fix", action="store_true", help="apply safe repairs (rewrites frontmatter only; never deletes)")
    aud.add_argument("--ledger", type=Path, default=None, help="ledger used to judge how recently a skill was used")
    aud.add_argument("--json", action="store_true", help="print JSON instead of the human summary")

    args = parser.parse_args(argv)

    if args.command == "hosts":
        print(json.dumps({
            "supported": list_hosts(),
            "skill_roots": [str(p) for p in host_skill_roots() if p.is_dir()],
            "note": (
                "A host without telemetry is still supported for skill discovery and routing. "
                "Usage figures are only produced where the host actually persists them."
            ),
        }, ensure_ascii=False, indent=2))
        return 0

    if args.command == "telemetry":
        hosts = tuple(sorted(TELEMETRY_HOSTS)) if "all" in (args.host or []) else tuple(args.host or ())
        usage = collect_host_usage(since_days=args.since_days, hosts=hosts)
        payload = {
            "measured": True,
            "note": "Read from host session files on disk. Hosts without persisted usage are marked unavailable, not zero.",
            "hosts": usage,
        }
        if args.record:
            record = {
                "task_id": f"telemetry-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
                "phase": "after",
                "label": "host telemetry",
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "host_telemetry": usage,
                "actual_tokens": UNAVAILABLE,
                "actual_tokens_source": "host session files, per host",
                "router_version": VERSION,
            }
            append_ledger(record, base=(args.ledger.parent if args.ledger else None))
            payload["recorded"] = str(args.record)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "estimate":
        roots = [Path(r) for r in args.root] if args.root else None
        hosts = tuple(sorted(TELEMETRY_HOSTS)) if "all" in (args.host or []) else tuple(args.host or ())
        payload = active_measurement(
            roots=roots, since_days=args.since_days, task=args.task, hosts=hosts,
            allowed=parse_scope(args.only),
        )
        if args.record:
            payload["ledger"] = str(append_ledger({
                "task_id": f"estimate-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}",
                "phase": "after",
                "label": "active measurement",
                "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "active_measurement": payload,
                "actual_tokens": UNAVAILABLE,
                "actual_tokens_source": "active walk of local files; no host asked",
                "router_version": VERSION,
            }, base=(args.ledger.parent if args.ledger else None)))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "update":
        if args.scan:
            payload = scan_upstreams(since_days=args.unused_days)
        else:
            payload = check_update(repo=args.repo, fetch=not args.no_fetch)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "audit":
        roots = [Path(r) for r in args.root] if args.root else default_roots(Path.cwd())
        result = audit_library(
            roots,
            unused_days=args.unused_days,
            fix=args.fix,
            ledger=(read_ledger(args.ledger if args.ledger else None)),
        )
        if not args.json:
            print(render_audit_text(result))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["counts"]["blocking"] == 0 else 1

    if args.command == "measure":
        roots = _roots(args)
        skills, _ = discover(roots)
        allowed = parse_scope(args.only)
        cost = measure_routing_cost(args.task, skills, allowed)
        baseline = measure_routing_cost(args.task, skills, None)
        task_id = args.task_id or new_task_id()
        record: dict[str, Any] = {
            "task_id": task_id,
            "phase": args.phase,
            "label": args.label or (args.task[:60] if args.task else ""),
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "with_aletheia": cost,
            "without_aletheia": baseline,
            "comparison": compare_scenarios(baseline, cost),
            "actual_tokens": args.actual_tokens if args.actual_tokens is not None else UNAVAILABLE,
            "actual_tokens_source": "host-reported" if args.actual_tokens is not None else UNAVAILABLE,
            "router_version": VERSION,
        }
        if args.note:
            record["note"] = args.note
        path = append_ledger(record, base=(args.ledger.parent if args.ledger else None))
        print(json.dumps({"ledger": str(path), **record}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "report":
        records = read_ledger(args.ledger if args.ledger else None)
        if args.json:
            print(json.dumps({"records": len(records)}, ensure_ascii=False, indent=2))
            print(render_report_html(records))
            return 0

        # Three delivery tiers: a URL when the file can be published, the file
        # itself, or formatted text. The format follows --format, then the
        # output extension, then HTML as the default.
        fmt = args.format
        out = args.out
        if fmt is None and out is not None:
            suffix = out.suffix.lower()
            fmt = {".md": "md", ".markdown": "md", ".txt": "text"}.get(suffix, "html")
        fmt = fmt or "html"

        if fmt == "md":
            body = render_report_markdown(records, as_text=False)
        elif fmt == "text":
            body = render_report_markdown(records, as_text=True)
        else:
            body = render_report_html(records)

        if out is None:
            # No destination: the point of this tier is to paste it somewhere.
            print(body)
            return 0

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(json.dumps({"report": str(out), "format": fmt, "records": len(records)},
                         ensure_ascii=False, indent=2))
        return 0

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
            return fail(str(e))
        print(payload["line"])
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.command == "context":
        transcripts = args.transcripts.expanduser() if args.transcripts else Path.home()
        if not transcripts.is_dir():
            return fail(f"transcript directory not found: {transcripts}")
        if args.window <= 0:
            return fail("--window must be > 0")
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
            return fail(str(e))
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
            return fail("--top must be > 0; --threshold must be >= 0")
        payload = route(args.task, skills, args.top, args.threshold)
        payload["issues"] = issues
        payload["scope"] = scope_payload
    else:
        try:
            cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
            assert isinstance(cases, list)
        except (OSError, ValueError, AssertionError) as e:
            return fail(f"invalid case file: {e}")
        details = []
        passed = 0
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("task"), str) or not isinstance(case.get("expect"), list):
                return fail("each case must have task:string and expect:string[]")
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

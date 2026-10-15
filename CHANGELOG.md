# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.4.0 — 2026-10-15

Aletheia becomes a **butler over the whole installed library**, and the owner
chooses once whether it decides or they do.

### Added

- **`inventory` subcommand**: the full registry with numbers the owner can pick
  from, plus `--query` to narrow large libraries and a `how_to_pick` hint.
- **`mode` subcommand**: read/write the persisted `auto` / `manual` preference
  in `aletheia-config.json`. Switching is one sentence, no reinstall.
- **`install.py --mode auto|manual`**: the owner chooses once at install; the
  bootstrap block records it so it survives across sessions.
- **`lint --strict`**: opt back into failing on advisory warnings.
- **`references/BUTLER.md`**: inventory measurements, mode behaviour, numbered
  selection, and what the butler still will not do.

### Fixed

- **Plugin-cache skills were invisible.** Discovery walked exactly one level, so
  the common `cache/<vendor>/<plugin>/<version>/SKILL.md` layout (three levels)
  was never reached. Unique routable skills on this machine went from **186 to
  233**; the walk is still bounded and still refuses symlinks.
- **`~/.workbuddy/skills` and the plugin cache were not in the default roots**,
  so a bare `scan` could miss the host's own installed library.
- **Name/directory mismatches no longer drop a skill.** The spec requires
  `name` to match the folder, but 27 real installs break it
  (`foo__skillhub`, `foo-skill`, `skill_<id>`). These are now warnings and the
  skill stays in the registry under its declared name.
- **`allowed-tools` written as a list** is tolerated with a warning instead of
  being rejected.
- **Inventory de-duplicates by name**, so a quoted number can never point at an
  ambiguous pair when a skill is installed twice.

### Measured impact

298 installed → **233 unique** skills (65 duplicate installs across personal
and plugin locations), 76.9 KB of metadata. Previously 186 were routable.

## 1.3.0 — 2026-10-15

### Added

- **`references/SCOPE_CONTROL.md`**: measured guidance on choosing which skills
  to switch on, with a decision table (on vs off) and verification steps.
- **`--profile` flag**: load a named allowlist from
  `.aletheia/profiles/<name>.json`, so a recurring workflow does not need its
  scope retyped. A missing profile fails loudly instead of silently scoping to
  nothing.
- **`scope.context_estimate`**: reports metadata bytes before/after scoping and
  the percentage saved, so the cost of an unscoped library is visible rather
  than theoretical.
- **`--scope-detail`**: opt back into listing every suppressed skill name.

### Fixed

- **`suppressed_skills` no longer printed by default.** On a real 186-skill
  inventory the name list cost ~3.9 KB — spending much of the context that
  scoping had just saved. The default now reports a count.
- **`--only` no longer fails silently.** An allowlist entry matching nothing
  (typo, or a skill that failed metadata lint) looked identical to "no relevant
  skill exists". It now returns `unmatched_allowed` plus a warning.
- Output size for a 3-skill scope dropped from 11.4 KB to 6.6 KB on that same
  inventory.

### Measured impact

On a 186-skill inventory: metadata 58.6 KB (~17k tokens) unscoped, ~0.98 KB
scoped to 3 skills — a 98.3% reduction. Suppressing the name list was worth a
further ~4 KB.

## 1.2.0 — 2026-10-15

### Added

- **Progress reporting** (`references/PROGRESS.md` + `router.py progress`):
  renders a task bar from a declared step list. Progress is only ever
  `finished steps / declared total` — never an extrapolation.
- Four distinct states: `working`, `blocked`, `failed`, `done`. `blocked`
  (waiting on a human decision) is deliberately separate from `failed` so a
  confirmation gate does not read as an error.
- Machine-readable output including per-step status, plus `--ascii` glyph
  fallback for terminals without box-drawing characters.

### Changed

- `SKILL.md`, `TRANSPARENCY.md` and both master prompts now cover progress
  reporting alongside the existing five-stage trace.
- Repository URLs point at `github.com/Xiranwuxianxi/aletheia`.

### Honesty constraints

- **No ETA field exists.** An agent cannot know how long the next step takes, and
  a wrong ETA is worse than none. This follows the same rule that governs context
  percentages.
- 100% requires verification, never "it probably worked".
- The bar advances at stage boundaries, not on every message; small tasks get no
  bar at all.

## 1.1.0 — 2026-10-15

### Added

- **Transparency protocol** (`references/TRANSPARENCY.md`): five-stage disclosure
  (intent → candidates → decision → operations → verdict), a mandatory
  disclosure format, and stop-gate criteria for destructive, outward-facing,
  financial and ambiguous actions. Rejected candidates must now be named.
- **Session scoping**: `--only` / `--session` on `scan`, `route` and `lint`, plus
  an optional `aletheia-session.json` manifest. Withheld skills are reported as
  `suppressed_skills`, never dropped silently. Scoping is explicitly a routing
  filter, not a security boundary.
- **`context` command**: grades context pressure from measured on-disk transcript
  bytes and returns the correct `/compact` or `/new` command for Claude Code,
  Codex, WorkBuddy or a generic host. Reports
  `is_measured_context_percentage: false` because no host token telemetry is
  available — the number is an estimate and is labelled as one.
- `examples/aletheia-session.example.json` documenting the session manifest.
- `README.md` (English, default) and `README.zh-CN.md` with a language switcher.
- `prompts/MASTER_PROMPT.en.md` — English resident prompt matching the Chinese one.

### Changed

- **Project renamed to Aletheia** (Ἀλήθεια, *unconcealment*), chosen because it
  names the project's actual purpose: turning black-box execution into something
  a user can inspect and supervise. Skill directory is now `skills/aletheia/`.
- `SKILL.md` now leads with transparency and stop gates rather than burying them
  in references.
- Both master prompts gained trace-disclosure, stop-gate, context-tier and
  session-scoping sections.

### Fixed

- README FAQ rendered literal `\n` sequences instead of line breaks (1.0.0).

### Security

- Stop gates define what must never be auto-executed without confirmation, while
  explicitly *not* gating reversible local reads — over-gating trains users to
  approve without reading.
- Context percentages are never presented as measured without real telemetry.

## 1.0.0 — 2026-10-14

### Added

- Agent Skills-compliant `skill-orchestrator` skill with a concise `SKILL.md`
  entry point and progressive-disclosure `references/`.
- Chinese master prompt (`prompts/MASTER_PROMPT.zh-CN.md`) for always-on routing.
- Read-only, stdlib-only CLI: `scan`, `route`, `lint` and offline `eval`.
- Conservative, non-destructive installer for Codex and Claude Code with an
  opt-in `--bootstrap` block that never overwrites existing project rules.
- Bilingual retrieval regression cases, six fixture skills and unit tests.
- GitHub Actions CI across Python 3.10 / 3.12 / 3.13.
- Community health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`.
- `docs/ARCHITECTURE.md`, `docs/EVALUATION.md` and `docs/RELEASE_CHECKLIST.md`.

### Changed

- Repository restructured to a standard open-source root layout; the skill now
  lives at `skills/skill-orchestrator/` and documentation references were updated.
- CLI and `eval` now share named threshold/top constants so reported retrieval
  quality matches real CLI behavior.
- `discover()` logic extracted into a documented `_skill_files()` helper for
  readability; no behavior change.
- `pyproject.toml` declares build backend, license file, project URLs and
  explicit zero runtime dependencies.

### Fixed

- README FAQ rendered literal `\n` sequences instead of line breaks.

### Security

- Discovery remains read-only: no skill code is executed, no network calls are
  made, and symlinked skill roots are refused.

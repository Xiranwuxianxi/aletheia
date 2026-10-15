# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.5.0 — 2026-10-15

Honest measurement across every host, plus lifecycle management for the library
itself — not just for the current conversation.

### Added

- **`telemetry` subcommand**: reads **real** token usage from every host that
  persists it. Claude Code (`message.usage`) and Codex (top-level `usage`) both
  work; WorkBuddy does not persist usage and is reported `unavailable` rather
  than `0`. Cache reads are listed separately from fresh input because they cost
  a fraction of it.
- **`measure` subcommand**: records a before/after measurement to a local ledger
  (`~/.aletheia/ledger.jsonl`), and quantifies the metadata saved by scoping.
  `--actual-tokens` is only ever a number you read from the host.
- **`audit` subcommand**: library health across broken, stale and duplicated
  skills, with `--fix` for provably safe repairs.
- **`mode` persistence helper** for the auto/manual preference.
- **`report` subcommand**: exports a self-contained HTML comparison — no CDN, no
  fonts, no network. Measured values are badged, estimates carry an `est`
  marker, unavailable cells say so in words.
- **`scripts/daily_check.py`**: cross-platform daily health check with a rotating
  local log. Read-only by default; exits `1` only when a human decision is needed,
  so a scheduler can alert on it. Scheduling recipes for Task Scheduler and cron
  are in `references/MEASUREMENT.md`.
- **`references/MEASUREMENT.md`**: what is measurable per host, how the
  comparison works, and the seven honesty rules.
- **`docs/sample-report.html`**: a generated example report.

### Fixed

- **CRLF documents defeated the repair logic.** Windows checkouts are CRLF, and a
  regex written against bare `\n` silently failed to match — the repair appeared
  to run but changed nothing. Repairs now normalise line endings, preserve the
  original convention on write, and reproduce the body verbatim.
- **A repaired `allowed-tools` block could produce invalid YAML** (missing blank
  line before the closing fence) or a duplicated fence. Both are covered by tests.
- **Audit identified skills by folder name**, so plugin version directories such
  as `5.8.2-wb.39298511.g37a65c0b` were counted as skill names — inventing 88
  phantom duplicates. It now uses the declared `name`.
- **Telemetry hosts returned inconsistent shapes**, so a consumer had to branch
  on which host lacked data. Every host now returns the same keys.

### Honesty constraints

- A host with no telemetry reads `unavailable`, never `0`.
- Savings that require an A/B run (redoing a wrong skill, money saved) are
  **refused with a stated reason** instead of being estimated.
- Cache reads are never blended into a single misleading total.
- `--actual-tokens` is supplied by a human; the tool will not derive it.

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

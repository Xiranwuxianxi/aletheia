# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.10.0 — 2026-10-16

Update detection, and an honest accounting of what cannot be updated at all.

### Added

- **`update` subcommand**: compares this checkout against its remote and reports
  whether something is newer. `--scan` extends that to every installed skill,
  listing which have a reachable upstream and which do not; `--no-fetch` reports
  local state without touching the network.
- **Git tags for `v1.8.0` through `v1.10.0`**, each pointing at the commit that
  actually shipped that version. Update detection compares versions, so it needs
  something to compare against — and a repository that cannot detect its own
  updates cannot honestly claim to be maintainable. A test fails if the current
  version is untagged.
- **`daily_check.py` reports update status**, and exits non-zero when an update
  is available, so the existing scheduler surfaces it without configuration.
- Both READMEs document the feature in full.

### Design: detection only, no `--apply`

There is deliberately no way to make this command change a file. Rewriting a
`SKILL.md` that another agent is currently reading is a bad trade — the reader
gets a half-written file, and the user never asked for that risk. A test
enforces the absence of `--apply`, `--install` and `--force`, and checks that the
git helper is never called with a mutating subcommand.

When an update exists the output hands over the decision:

```bash
git log HEAD..origin/main --oneline    # read what changed, first
git pull --ff-only origin main
python -m unittest discover -s tests   # verify before trusting it
```

### Measured on this machine

```text
252 unique skills · 2 with a git upstream · 250 with none recorded
```

**Most skills cannot be checked for updates at all**, because nothing records
where they came from. A skill dropped into `~/.agents/skills/` has no origin
URL, no version field, no manifest. The scan reports that gap rather than
guessing a repository — **250 skills without provenance is a finding, not a
bug**, and it identifies exactly which ones will silently go stale.

### Honesty constraints

- No network, no tags, or not a repository all report `update_available:
  "unavailable"` with a stated reason. None of them report `false`, because
  "no update" and "could not check" are different claims.
- A non-tagged version is not treated as an error; `git describe` reporting a
  tag behind HEAD is normal while fixes are unreleased.

### Fixed

- `check_update` accepted any path and let git walk upward to an unrelated
  repository, so a directory that was not a repo at all still passed every git
  call. An explicit path must now actually contain `.git`.

90 tests pass. lint `ok: true`, eval 16/16.

## Unreleased

Fixes from a review of v1.9.0. No version bump: these are corrections to
existing behaviour and documentation, not a new feature.

### Fixed

- **The Windows symlink test errored instead of skipping.** Creating a symlink on
  Windows needs Administrator or Developer Mode; without it the test raised
  `OSError [WinError 1314]`. That is an environment limitation, not a defect, and
  a permanent unrelated error hides real regressions behind it. The test now
  probes the capability and calls `skipTest`.
- **Four documents contradicted the code on scope precedence.** The code has
  always intersected (`&` for both the manifest and the profile), but the docs
  said `--only` "overrides" — in the same sentence that also said "intersect".
  All four now state it unambiguously: multiple scope sources are intersected; a
  skill is in scope only if every source that named it named it. The fourth
  location was `references/TRANSPARENCY.md`, which the review list missed.
- **Two error protocols for one failure class.** `parser.error()` (stderr, exit 2)
  was mixed with JSON `{"error": ...}` (stdout, exit 2), so a machine caller had
  to handle both. Business-logic failures now go through one `fail()` helper.
  Argparse still owns genuine argument-parsing errors, which happen before any
  command semantics exist.
- **A dead `--json` flag.** `scan`/`route`/`lint` accepted it and never read it —
  they always emitted JSON. Removed, matching the actual contract. Both READMEs
  now state it plainly.
- **The Chinese README's opening sentence was half-translated** — "解蔽"
  followed by an untranslated English *principles*. Rewritten.
- **A duplicated CHANGELOG entry.** The 1.1.0 and 1.0.0 sections carried the same
  README `\n` fix verbatim. The 1.0.0 record is untouched; the 1.1.0 entry is
  now written as an explicit regression, because a repeat is a signal the
  original fix lacked a guard — not a duplicate to dedupe away.
- Cleared `__pycache__` from `skills/aletheia/scripts/` and `tests/`.

### Changed

- **CI matrix now spans ubuntu-latest, macos-latest and windows-latest**, with
  `fail-fast: false` so one platform's failure does not hide the others. The
  line-ending and path-separator bugs this project hit were invisible on Linux,
  so a Linux-only matrix cannot be trusted to catch them. The newest interpreter
  runs on every platform; older ones are spot-checked on Linux.
- `tests/test_router.py` gained three guards: business errors are JSON on stdout
  with exit 2; `--json` is genuinely rejected; scope sources intersect and no doc
  still says "overrides".
- Two documentation guards added: no untranslated English fragments in the
  Chinese README's opening, and no verbatim duplicate CHANGELOG entries. Both
  were verified to fail when the defect is reintroduced.

85 tests pass. lint `ok: true`, eval 16/16.

## 1.9.0 — 2026-10-16

Measurement stops depending on hosts volunteering their numbers.

### Added

- **`estimate` subcommand**: walks this machine and measures everything
  measurable **without asking any host for anything**.
  - token usage, read from every host that persists it
  - metadata actually loaded into context, counted from the visible skills
  - the skill-body pool, every `SKILL.md` read and measured
  - duplicate installs, by comparing install paths against declared names
  - host activity, as bytes written to log directories in a window
  - `--only` to measure the scoped cost, which is the number a butler needs
- `daily_check.py` now runs the active walk and reports it, so the daily log
  carries measurement that does not depend on any host.
- Both READMEs document it in full.
- `MEASUREMENT.md` gains an "Active measurement" section.

### Measured on this machine

```text
input 11,365,980 · output 1,978,510 · cache_read 364,126,214 · cache_write 483,380
completeness: partial — 10 host(s) persist no token counter
library: 252 unique skills (708 duplicate installs)
whole-library metadata: 44,322 est. tokens
scoped to 2 skills:          347 est. tokens   — a 99.2% reduction
```

### Honesty constraints

- **Host-internal reasoning tokens are `unavailable`, not estimated.** They are
  never written to disk, and no amount of local inspection recovers a number that
  was never recorded.
- **Billed cost is `unavailable`.** It needs a model id and a price table. No
  price table is bundled on purpose: a stale table silently becomes a
  confidently wrong money figure.
- **Log growth is bytes and is labelled as such**, never summed into a token
  total. A test asserts no numeric token field can appear on a byte-level record.
- **De-duplicated before counting.** A skill installed in four agent directories
  is one cost, not four.

### Fixed

- **The active total silently read zero.** The canonical buckets are
  `cache_read`/`cache_write` while `collect_host_usage` returns
  `cache_read_tokens`/`cache_write_tokens`; reading the wrong key produced a
  confident `0`. Exactly the failure this project exists to prevent, present in
  the feature meant to prevent it. A test now guards the mapping.
- **`active_measurement` had no `home` parameter**, so it always read the real
  `Path.home()` and a test could never isolate itself. Found because a test
  asserting 111 tokens was getting the machine's real Claude figures.

80 tests pass.

## 1.8.2 — 2026-10-16

Both READMEs brought up to date with v1.8, plus a guard so they cannot drift
apart silently again.

### Added

- **Both READMEs document what shipped in v1.8**:
  - the host table now lists all **fourteen** hosts with each one's skill
    directory, rather than twelve hosts and no paths
  - SQLite-backed hosts (OpenClaw, Hermes) explained: read directly, `sqlite3` is
    standard library so no dependency is added, opened read-only via URI
  - **"One library, several agents"** — the fourteen skill directories Aletheia
    scans, and the real finding that mirroring a library across agents produces
    17 duplicate installs and drift
  - **"Works on Windows, macOS and Linux"** — the per-platform table, and both
    portability bugs CI caught, because a reader deciding whether the tool fits
    their machine needs to know it does
  - the zero-dependency guarantee, with the command that proves it
  - measured numbers: 252 unique skills, 960 install locations, 14 hosts, 4 with
    measured telemetry
  - nine install locations for the skill itself, up from two

### Fixed

- Host names in the READMEs did not match the registry: `Copilot CLI` vs
  `GitHub Copilot CLI`, `Droid` vs `Factory Droid`, `Hermes` vs `Hermes Agent`. A
  reader searching for their tool would not have found it.

### Tests

Two new guards, both of which caught a real problem the moment they were added:

- **`test_bilingual_readmes_stay_in_step`** asserts on *facts* rather than prose,
  because wording legitimately differs between languages. Every registered host
  label must appear in the English README; every capability fact (host count,
  SQLite support, the zero-dependency script, cross-platform handling) must
  appear in both; and both files must reference the same `references/` set. It
  immediately flagged the missing zero-dependency mention and three mismatched
  host names.
- **`test_readme_links_resolve`** checks every relative link in both files, so a
  documentation path cannot rot unnoticed.

75 tests pass.

## 1.8.1 — 2026-10-16

A test bug, caught by CI, that could only ever fail on Linux.

### Fixed

- **`test_paths_are_handled_with_both_separators` asserted the impossible.** It
  built a path and swapped `/` for `\`, expecting discovery to find the skill.
  That is true on Windows, where both separators work. On Linux `\` is an
  ordinary filename character, so `\tmp\...` is simply not a path — the test was
  asserting that nonsense resolves correctly. The test now branches on `os.name`:
  forward slashes must work everywhere, the escaped form is asserted only on
  Windows, and on POSIX a backslash path must resolve to **nothing** rather than
  quietly matching something unintended.

  No production code changed. `router.py` was correct on both platforms.

### Tests

- A structural guard now requires any test that manipulates path separators to
  branch on `os.name`. Verified to fire: neutralising those branches makes the
  suite fail, restoring them makes it pass.
- The lesson is recorded in the guard's docstring: a test that passes only on
  the author's machine is worse than no test, because it reports confidence it
  has not earned.

73 tests pass.

## 1.8.0 — 2026-10-16

Adds Hermes and OpenClaw, and fixes two portability bugs that only CI could see.

### Added

- **OpenClaw and Hermes adapters** — 14 hosts registered. Both keep usage in
  **SQLite**, so the adapters read it directly. Python's `sqlite3` is standard
  library, so this adds **no dependency**; the zero-dependency guarantee holds.
  Databases are opened **read-only via URI**, because a telemetry reader must
  never mutate or lock a host's store.
- A declarative `sqlite` block per host: path, glob, table and column aliases,
  mapped onto the same canonical buckets as the JSON adapters.
- **Multi-agent skill discovery.** Both agents keep their own `skills/`
  directory, and in practice these mirror the WorkBuddy library. On this machine
  OpenClaw's 13 skills were previously **completely invisible**; Hermes holds
  194 of 201. Both are now reachable.
- `tests/zero_dependency_check.py`: 13 assertions proving the no-PyYAML path
  reaches the same verdict as the PyYAML path.
- A CI job (`no-pyyaml`) that runs the full check with only the standard
  library, plus a parity step in the main matrix.
- Cross-platform tests: CRLF preservation, mixed path separators, SQLite
  read-only semantics, and a missing-table case.

### Fixed

- **CRLF was silently lost on every repair.** Python's text mode translates CRLF
  to LF when reading, which makes every comparison CRLF-safe but also *erases the
  evidence* of which convention the file used — so repaired files always came
  back as LF, showing as a whole-file diff on Windows. The convention is now read
  from the bytes on disk and preserved.
- **The no-dependency path disagreed with the PyYAML path.** A list-style
  `allowed-tools` was classified `invalid_yaml` without PyYAML (items were
  silently dropped by the fallback parser) but `allowed_tools_list` with it. That
  is why CI failed while every local run passed. Both paths now detect the same
  conditions, and repairs work without PyYAML at all — the fallback parser
  collects block sequences instead of discarding them, and two textual repairers
  replace the ones that required a YAML library.
- Over-long descriptions in **folded block scalars** (`description: >`) were not
  detected without PyYAML, because only the first line was measured.

### Measured on this machine

`960 installed → 252 unique (708 duplicate installs)`. Auditing just the two new
agents: `213 scanned, 210 healthy, 3 broken, 17 duplicated` — the duplication
being a genuine finding, since a library mirrored across agents drifts.

### Notes

- SQLite teardown on Windows can leave a file briefly held open, so those two
  tests use `ignore_cleanup_errors` — otherwise a locked handle fails an
  unrelated assertion.
- Adapters track each tool's file format. An unrecognised layout, missing table
  or absent column reports `unavailable` with the reason — never a zero.

72 tests pass.

## 1.7.1 — 2026-10-15

Structure fix in `SKILL.md`, found by measuring instead of assuming.

### Fixed

- **Six core sections were accidentally demoted to `###`.** `Candidate
  discovery`, `Session scoping`, `Context pressure`, `Decision policy`,
  `Orchestration & context budget` and `Evidence standard` were nested *inside*
  "Progress reporting". A reader following progressive disclosure would have
  finished the progress-bar section and stopped — never reaching the routing
  rules. All six are top-level `##` again. This was a plain editing mistake of
  mine, and it hid the most important content in the file.
- **Progress reporting compressed** from a full table plus seven rules down to
  the three that carry the weight (no invented ETA, 100% means verified, small
  tasks get no bar). The state table and anti-patterns were already in
  `references/PROGRESS.md`, so the detail was duplicated for no gain.

### Tests

Four structural guards, so this class of mistake cannot recur:

- Every core capability must be a top-level `##`. Verified to actually fail by
  demoting `Decision policy` and watching the suite catch it.
- `SKILL.md` must stay under the spec's 500-line guidance. It is 240.
- The frontmatter `description` must keep headroom under 1024 chars — currently
  714, so the skill can still grow.
- Every `references/*.md` named in `SKILL.md` must exist, so a pointer is never
  dangling.

66 tests pass.

### On the earlier claim

A previous note said `SKILL.md` was "2400+ lines". That was wrong — it
conflated `router.py` (2,443 lines of code) with `SKILL.md`. At 247 lines it was
already well within the spec's guidance, so no size-driven rewrite was needed.
The real problem was the section hierarchy, which measurement surfaced.

## 1.7.0 — 2026-10-15

Reports gain a third delivery tier, because "can't publish a URL" is a delivery
problem — not a reason to ship something unreadable.

### Added

- **`report --format html|md|text`**: the same data rendered three ways.
  - `html` (default) — a self-contained page that opens offline
  - `md` — for pasting into an issue, doc or PR
  - `text` — for a chat message or terminal, with Markdown syntax stripped but
    all column structure, heading rules and provenance labels intact
- **Format inferred from the output extension** (`.html` / `.md` / `.txt`), so
  `--out report.md` "just works". With no `--out`, the report prints to stdout —
  which is the point of the text tier.
- `docs/sample-report.md` alongside the HTML example.

### Changed

- The text tier is a **formatted document**, not a dump: heading rules, aligned
  columns, a provenance legend, and every figure labelled measured / estimated /
  unavailable. Degrading to a bare list of numbers is not offered as a mode.

### Fixed

- **The headline could show em-dashes while a real comparison sat one line
  above it.** Both renderers read `records[-1]`, but a telemetry record carries
  no comparison. They now take the newest record that actually has one.
- **The plain-text tier leaked Markdown syntax** — `**` for bold and backticks
  survived into the output. Both are now stripped properly rather than by naive
  character removal.

### Tests

- Assert the HTML report contains no `http://`, `https://`, `<script` or `cdn`:
  a report that needs the network fails precisely when it matters — offline, in
  an archived attachment, or behind a proxy. This cannot regress.
- Assert the text tier keeps its structure and leaks no Markdown.
- Assert the headline is not blanked out by a trailing telemetry record.
- Assert an empty ledger renders in all three formats rather than crashing.

62 tests pass.

## 1.6.0 — 2026-10-15

Aletheia now covers the mainstream agent hosts, not just the two it was built
against. Each was verified against the layout that tool actually writes.

### Added

- **Twelve host adapters** in a declarative registry: Claude Code, Codex, Kimi
  Code, Qwen Code, Gemini CLI, GitHub Copilot CLI, OpenCode, Factory Droid,
  Kiro, Crush, Aider and WorkBuddy.
- **An alias table** normalising every host's field names onto one shape
  (`input · output · cache_read · cache_write`). This is the part that matters:
  hosts disagree on *everything*.
- **`hosts` subcommand**: what is supported, which can be read, and each host's
  native skill directory.
- **Multi-glob per host**, so a tool that writes several layouts is still found.
- **Skill discovery across hosts**: `default_roots` now includes every supported
  host's skill directory. Unique skills visible on this machine went from
  **233 to 252**, since skills installed under a different agent are now seen.
- Tests that guard the registry structurally: every alias must be reachable by
  the line prefilter, and every host must return an identical key set.
- `references/MEASUREMENT.md` documents each host's session path, usage block and
  field names, plus how to add one without touching code.

### Measured on this machine

| Host | Files | Messages | Input | Output | Cache read |
| --- | --- | --- | --- | --- | --- |
| Claude Code | 2 | 29 | 58 | 8,951 | 2,377,969 |
| Codex | 141 | 1 | 180 | 96 | 48 |
| Kimi Code | 49 | 3,401 | 8,842,282 | 1,917,619 | 359,392,132 |
| Qwen Code | 4 | 106 | 2,523,460 | 51,844 | 2,356,065 |

Gemini CLI, Copilot CLI, OpenCode, Droid, Kiro, Crush and Aider report
`unavailable` on this machine — some because they are not installed, and
WorkBuddy because it persists no usage at all.

### Fixed

- **A synthesized cache-read zero could overwrite a real logged value.** Codex
  carries `cached_tokens` under `input_token_details`; when that lookup failed,
  a `0` was written over the true figure — understating cost by orders of
  magnitude. Only a present, non-zero nested value is now merged.
- **The line prefilter could drop a real usage line.** It keyed on `"token"` or
  `"usage"` only, so a line carrying just `cache_read_input_tokens` was skipped.
  The prefilter is now derived from each host's own declaration, so a newly
  added alias cannot be filtered out by accident.
- **Codex cache reads were invisible** because the nested detail object sits
  *beside* `usage`, not inside it.

### Known limits, stated plainly

- OpenCode and Goose keep usage in SQLite. Aletheia is stdlib-only and reads only
  their JSON message stores; when none exists the host reports `unavailable`.
- Adapters track each tool's file format, which can change without notice. An
  unrecognised layout reports `unavailable` with a reason — never a zero.

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

- **Regression:** the README FAQ rendered literal `\n` sequences instead of line
  breaks — the bug fixed in 1.0.0 reappeared during the bilingual rewrite and
  was fixed again. Recorded separately because a repeat is a signal that the
  original fix lacked a guard, not a duplicate to be deduplicated away.

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

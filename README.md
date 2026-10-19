<div align="center">

# Α Aletheia

**Unconcealment for agent skill routing.**
*Route to the right skill — and show your work while you do it.*

[![License: MIT](https://img.shields.io/badge/license-MIT-534AB7?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-1D9E75?style=flat-square)](https://www.python.org/)
[![Agent Skills](https://img.shields.io/badge/spec-Agent%20Skills-BA7517?style=flat-square)](https://agentskills.io/specification)
[![Version](https://img.shields.io/badge/version-1.13.1-888780?style=flat-square)](CHANGELOG.md)

**English** · [简体中文](README.zh-CN.md)

</div>

---

Aletheia (Ἀλήθεια) is the Greek principle of **unconcealment** — truth as that
which is *not hidden*. It is the precise antonym of a black box, which is
exactly the problem this project solves: agents that silently pick a skill, run
something, and hand you a result you cannot audit.

Aletheia routes tasks to the right installed skills **and makes the routing
visible**: what was considered, what was rejected and why, what actually ran,
what was verified, and what was not. It stops and asks before anything
irreversible or outward-facing.

## Why

Three failure modes show up again and again in agent work:

| Failure | What it looks like | Aletheia's answer |
| --- | --- | --- |
| **Silent selection** | A specialized skill existed, but the agent improvised from general knowledge | Mandatory preflight + candidate disclosure |
| **Wrong pick** | The agent matched on keywords and grabbed the wrong skill | Show rejected candidates and the reason |
| **Unauditable execution** | "Done." — with no trace of what ran or what was checked | Five-stage trail: intent → candidates → decision → operations → verdict |

Plus the two that make long sessions painful: **drifting context** and
**skill-library noise**.

## What you get

- **A butler over your whole library** — knows every installed skill, in personal dirs *and* plugin caches
- **You decide who chooses** — autonomous by default, or take over and pick by number; chosen once, switches in one sentence
- **Visible routing** — five disclosure stages, including *rejected* candidates
- **Countable progress** — a bar that reports finished steps out of a declared total, in four states, with no invented ETA
- **Stop gates** — confirmation before destructive, outward-facing, financial or
  ambiguous actions; never gate on harmless local reads
- **Session scoping** — run only the skills this task needs, not the whole library
- **Context pressure** — measured transcript bytes, graded tiers, and the exact
  `/compact` or `/new` command for your host
- **Read-only CLI** — stdlib-only inventory, discovery, routing, scope, progress and offline eval

## Install

```bash
git clone https://github.com/Xiranwuxianxi/aletheia.git
cd aletheia

python scripts/install.py --list          # the 17 hosts and where each reads instructions
python scripts/install.py --scope user --bootstrap --dry-run
python scripts/install.py --scope user --bootstrap
```

| Flag | Meaning |
| --- | --- |
| `--host` | a host key or label, repeatable; default is every host installed on this machine |
| `--scope` | `project` (beside the code) or `user` (every project) |
| `--list` | print every known host with its skill directory and instruction file |
| `--dry-run` | preview every write before it happens |
| `--force` | back up a differing install before replacing it |
| `--bootstrap` | write the marked routing block into each host's own instruction file |

```bash
# just one host
python scripts/install.py --host kimi --scope user --bootstrap

# beside a codebase instead of globally
python scripts/install.py --host codex --scope project --project /path/to/my-project --bootstrap

# pick skills by number instead of letting it choose
python scripts/install.py --scope user --bootstrap --mode manual
```

**Every host in the registry is installable.** The previous installer knew two
while the registry tracked seventeen, so the hosts actually in use had no path at
all.

Three hosts get the skill directory but no routing hook, because no instruction
file for them could be verified and a guessed filename would be worse than none:

| Host | Why |
| --- | --- |
| **WorkBuddy** | its instruction surface is `SOUL.md`, which is your identity file — never written |
| **OpenClaw** | reads `AGENTS.md` from its own workspace; the path was not confirmed |
| **Aider** | its `read:` list is a config setting, not a conventional file |

The installer says which host it skipped and why, per host, in its output.

### What it refuses to do

- **Overwrite a different install** without `--force`, and back it up rather than
  deleting it.
- **Write through a symlink**, at the target or at the instruction file.
- **Touch `SOUL.md`, `USER.md`, `IDENTITY.md` or `MEMORY.md`.** Those describe the
  user; a routing hook does not belong there and the damage is not recoverable.
- **Guess.** A host with no verified instruction file gets the skill and a stated
  reason, not an invented filename.

Re-running is idempotent: the hook lives between markers and is upserted, never
appended twice. Try `--dry-run` first.

<details>
<summary><b>Route B — install just the skill</b></summary>

Copy `skills/aletheia/` into wherever your agent looks for skills:

| Agent | Project level | Personal level |
| --- | --- | --- |
| Codex | `.agents/skills/aletheia/` | `~/.agents/skills/aletheia/` |
| Claude Code | `.claude/skills/aletheia/` | `~/.claude/skills/aletheia/` |
| WorkBuddy | `.workbuddy/skills/aletheia/` | `~/.workbuddy/skills/aletheia/` |
| Hermes | — | `~/.hermes/skills/aletheia/` |
| OpenClaw | — | `~/.openclaw/skills/aletheia/` |
| Kimi Code | — | `~/.kimi/skills/aletheia/` |
| Qwen Code | — | `~/.qwen/skills/aletheia/` |
| Gemini CLI | — | `~/.gemini/skills/aletheia/` |
| GitHub Copilot CLI | — | `~/.copilot/skills/aletheia/` |
| pi | `.pi/skills/aletheia/` | `~/.pi/agent/skills/aletheia/` |
| Doubao Work | — | see the per-OS paths below |
| QwenWork | — | `~/.qwenworkcn/skills/aletheia/` |

**Doubao Work** follows the Electron app-data layout, so its skill directory is
spelled per OS (the Windows spelling is verified against a real install; macOS
and Linux follow each OS's convention and are registered as candidates):

```text
~/AppData/Local/DoubaoWork/User Data/Default/.doubaowork/agent_mode/workspace/.skills
~/AppData/Local/DoubaoWork/User Data/Default/.doubaowork/agent_mode/workspace/.user_skills
~/Library/Application Support/DoubaoWork/User Data/Default/.doubaowork/agent_mode/workspace/.skills
~/Library/Application Support/DoubaoWork/User Data/Default/.doubaowork/agent_mode/workspace/.user_skills
~/.config/DoubaoWork/User Data/Default/.doubaowork/agent_mode/workspace/.skills
~/.config/DoubaoWork/User Data/Default/.doubaowork/agent_mode/workspace/.user_skills
```

**QwenWork** (Qoder's house spelling) also reads
`~/.qwenworkcn/bin/computer-use/skills`, and its slash commands land in
`~/.qwenworkcn/commands`.

Then add one line to your project instructions:

> Before each substantive task, assess installed skills and use aletheia to select, read and actually apply relevant skills before execution.

</details>

## Hard guarantee: the hook

An instruction file is a *request*; a host hook is a *mechanism*. Wire
`skills/aletheia/scripts/hook_prompt_submit.py` into your agent's hook runtime
and the routing runs **before the model can decide anything**. By default it
fires twice per conversation:

- **`SessionStart`** — the first turn of every conversation: the routing
  protocol is injected before the first task is answered, so the first turn is
  covered even if nothing else runs.
- **`UserPromptSubmit`** — every prompt after that: aletheia runs retrieval over
  the installed library and injects the advisory candidates **for this prompt**.

WorkBuddy example (`~/.workbuddy/settings.json`; new entries need approval in
the `/hooks` panel before they take effect):

```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "python \"C:/path/to/aletheia/skills/aletheia/scripts/hook_prompt_submit.py\" || true", "timeout": 15 }] }
    ],
    "UserPromptSubmit": [
      { "matcher": "*", "hooks": [{ "type": "command", "command": "python \"C:/path/to/aletheia/skills/aletheia/scripts/hook_prompt_submit.py\" || true", "timeout": 15 }] }
    ]
  }
}
```

The script reads the event from the hook payload and answers with the documented
JSON envelope (`hookSpecificOutput.additionalContext`). It always exits 0 — a
hook must never block your message — and degrades honestly: if retrieval fails,
the output says so instead of inventing candidates. Prompt text is used
in-process and never echoed into the context or the process list.

**The owner decides — nothing is hardwired.** Every level may switch the hook
off or narrow which events inject, and the nearest declaration wins:

| Level | File | Example |
| --- | --- | --- |
| session | `aletheia-session.json` | mute one conversation: `{"hook": "off"}` |
| project | `aletheia-config.json` | `{"hook": "on", "hook_events": "session-start"}` |
| machine | `~/.aletheia/config.json` | the owner's default for this machine |

```bash
python skills/aletheia/scripts/router.py hook                          # what is active, and which file said so
python skills/aletheia/scripts/router.py hook --set off                # silence instantly
python skills/aletheia/scripts/router.py hook --set on                 # bring it back
python skills/aletheia/scripts/router.py hook --events session-start   # only the first turn injects
```

`--set off` is a true no-op switch: the hook stays wired but prints nothing —
no host settings edit, no re-approval round-trip. To remove the injection point
entirely, delete the entry from the host's settings file. The mode preference
(`mode`) and hook preferences share `aletheia-config.json`; writing one never
clobbers the other.

## Works on Windows, macOS and Linux

Standard library only — **nothing to install on any of the three**, `python3`
included on macOS and Linux. The differences that do exist are handled
explicitly rather than assumed:

| Concern | Windows | macOS / Linux |
| --- | --- | --- |
| Line endings | CRLF preserved on repair | LF preserved on repair |
| Path separators | both `\` and `/` accepted | `/` native; `\` is a filename character |
| Home directory | `Path.home()` → `%USERPROFILE%` | `$HOME` |
| sqlite locking | connections closed before teardown | advisory locks |
| Terminal glyphs | ASCII bar fallback | box-drawing bar |

Two of these were real bugs, and **CI found both** — they were invisible on the
developer's machine:

- **CRLF was silently lost on every repair.** Python's text mode translates CRLF
  to LF when reading, which makes every comparison CRLF-safe but also *erases the
  evidence* of which convention the file used. Repaired files always came back as
  LF, showing as a whole-file diff on Windows.
- **The no-dependency path disagreed with the PyYAML path.** A list-style
  `allowed-tools` was classified `invalid_yaml` without PyYAML but
  `allowed_tools_list` with it — so a skill passed locally and failed only on
  CI. A dedicated job now runs the whole suite with just the standard library,
  and a structural guard requires any separator test to branch on `os.name`.

The zero-dependency guarantee is load-bearing: it is what lets Aletheia run in a
fresh CI container, inside another agent's sandbox, or on a host with no package
manager — which is exactly where a routing tool is most useful.

```bash
# Prove it: run the same checks with PyYAML blocked
python tests/zero_dependency_check.py
```

That script asserts 13 things about the no-PyYAML path, and CI runs it as a
separate job. It exists because "zero dependencies" is a claim that decays
silently the first time someone reaches for a convenient import.

## Measured on one machine

| Metric | Count |
| --- | --- |
| Unique skills visible | **252** |
| Install locations scanned | 960 |
| Agent hosts registered | 17 |
| Hosts with measured token telemetry | 4 |

Earlier in development the same machine reported 186 unique skills, then 233, then
252 — each jump traced to a real defect: a one-level walk that missed nested
plugin caches, then host skill directories that were never scanned at all. The
numbers are in `CHANGELOG.md` with the cause of each.

## Transparency in practice

A real trace, compressed:

```text
Tracing: export the quarterly workbook to PDF
Skills considered:
  pdf-processing   selected — owns PDF output
  slides-design    rejected — wrong artifact type
  image-creation   rejected — scope mismatch
Operations:
  1. router.py route "export quarterly workbook to PDF"  → pdf-processing (52)
  2. read skills/pdf-processing/SKILL.md                 → 214 lines
  3. [GATE] overwrite Q3-report.pdf (2.1 MB, 3 days old)? → user chose "write v2"
  4. write Q3-report-v2.pdf                              → 12 pages, 1.8 MB
Evidence: file opens, 12/12 pages present, sha256 recorded
Not verified: visual fidelity against the original workbook
```

**Rejected candidates are mandatory.** Showing only what you picked hides the
most useful signal — whether a better option was silently passed over.

### Stop gates

```text
This will overwrite Q3-report.pdf (2.1 MB, modified 3 days ago).
  1 · Overwrite in place
  2 · Write Q3-report-v2.pdf and keep both   ← recommended
```

Gates fire for destructive, outward-facing, financial and ambiguous actions.
They do **not** fire for reading files, searching or running tests —
over-gating trains people to approve without reading.

## The butler: who chooses

Pick the mode **once**, at install:

```bash
# Autonomous (default): Aletheia decides, and shows what it rejected and why
python scripts/install.py --scope user --bootstrap --mode auto

# Owner-driven: Aletheia offers numbered candidates and waits for you
python scripts/install.py --scope user --bootstrap --mode manual
```

Either way the five-stage disclosure still applies — manual mode changes *who
decides*, not *what must be visible*.

Switch any time, no reinstall:

```bash
python skills/aletheia/scripts/router.py mode --set manual   # you take over
python skills/aletheia/scripts/router.py mode --set auto     # hand it back
```

Or just say it: *"你自己选"* / *"我自己选"* / *"换个状态"*.

### Answer by number

With a large library, listing everything would be unusable — so filter first:

```bash
python skills/aletheia/scripts/router.py inventory --query "quarterly deck" --limit 12
```

```text
Which skills should I use? Reply with a number, several (2,5), 'all', or 'none'.

 1. guizang-ppt-skill   editable PPTX generation
 2. excel-xlsx         spreadsheet read/write
 3. baoyu-slide-deck   image-rich slide decks
```

`3` single · `2 5` multiple · `all` everything listed · `none` no skill, just do
the task. Numbers are **per-invocation** — after an install they change, so the
list is always re-shown rather than reusing stale numbers.

### How much can it actually see?

```bash
python skills/aletheia/scripts/router.py inventory --limit 1
```

Discovery covers personal skill directories *and* nested plugin caches
(`<vendor>/<plugin>/<version>/SKILL.md`), and reports both installed and unique
counts. A `name` that differs from its folder — common with marketplace
suffixes like `foo__skillhub` — is reported as a **warning, not dropped**;
dropping those would hide real skills from routing.

## Progress you can trust

```text
[████████████░░░░░░░░░░░░]  50%  2/4  → writing report
```

A progress bar is the easiest thing in an agent UI to turn into a lie. Aletheia
renders progress as **finished steps out of a declared total** — nothing else.

| State | Means | Bar |
| --- | --- | --- |
| `working` | Steps are advancing right now | Filled to the current step |
| `blocked` | **Waiting on your decision** — not an error | Filled to the stall point |
| `failed` | Cannot proceed | Filled to where it stopped |
| `done` | All steps finished **and verified** | Full, `✓ N/total` |

`blocked` is deliberately distinct from `failed`. Waiting at a confirmation gate
is a healthy pause; rendering it as an error trains people to panic-click.

```bash
python skills/aletheia/scripts/router.py progress \
  "gather sources" "read SKILL.md" "write report" "verify output" \
  --done 2 --current "writing report"
```

Rules: declare steps before starting · count only finished steps · advance at
stage boundaries, not every message · **no ETA field exists** · 100% means
verified · omit the bar for small tasks.

## Measuring what it actually costs

```bash
python skills/aletheia/scripts/router.py hosts        # what is supported
python skills/aletheia/scripts/router.py telemetry    # real totals
python skills/aletheia/scripts/router.py report --out report.html
```

Seventeen mainstream hosts are registered. **Every host returns the same keys**,
and one we cannot read is reported `unavailable` — never `0`.

| Host | Telemetry | Skill dir (project) | Host | Telemetry | Skill dir (project) |
| --- | --- | --- | --- | --- | --- |
| Claude Code | measured | `.claude/skills` | **OpenClaw** | SQLite | `.openclaw/skills` |
| Codex | measured | `.agents/skills` | **Hermes Agent** | SQLite | `.hermes/skills` |
| Kimi Code | measured | `.kimi/skills` | OpenCode | JSON store | `.opencode/skills` |
| Qwen Code | measured | `.qwen/skills` | Factory Droid | measured | `.factory/skills` |
| Gemini CLI | measured | `.gemini/skills` | Kiro | measured | `.kiro/skills` |
| GitHub Copilot CLI | measured | `.copilot/skills` | Crush | measured | `.crush/skills` |
| Aider | if enabled | `.aider/skills` | WorkBuddy | none persisted | `.workbuddy/skills` |
| pi | measured | `.pi/skills` | Doubao Work | none persisted | app-data `.skills` |
| QwenWork | none persisted | — | | | |

Each host names its fields differently — Claude logs `cache_read_input_tokens`,
Codex hides `cached_tokens` inside `input_token_details`, Kimi uses
`input_cache_read` under `message.payload.token_usage`, Qwen and Gemini use
`promptTokenCount`. Adapters map them onto one shape via an alias table; a layout
that is not recognised reports `unavailable` rather than a confident zero.

**SQLite-backed hosts** (OpenClaw, Hermes) are read directly — Python's `sqlite3`
is standard library, so this adds **no dependency**, and databases are opened
**read-only via URI** because a telemetry reader must never mutate or lock a
host's store.

Adding a host is a data change, not a code change: append to `TELEMETRY_HOSTS`,
then run the tests. See
[`references/MEASUREMENT.md`](skills/aletheia/references/MEASUREMENT.md).

Measured on one machine:

```text
host                  ok  files  msgs           input      output    cache_read
Claude Code           Y   2      29                58       8,951     2,377,969
Codex                 Y   141    1                180          96            48
Kimi Code             Y   49     3401       8,842,282   1,917,619   359,392,132
Qwen Code             Y   4      106        2,523,460      51,844     2,356,065
Gemini CLI            -   0      -                              unavailable
```

Cache reads are counted separately from fresh input because they cost a fraction
of it; blending them would misstate cost by an order of magnitude. The **tokens**
figure — the one reported everywhere, in every format — is input + output +
cache write, and never cache reads.

**What is refused rather than estimated:**

| Claim | Why not |
| --- | --- |
| Tokens saved by not redoing a wrong skill | Needs a real A/B run on the same task |
| Actual usage with vs without | No telemetry on that host |
| Money saved | Needs a price and a measured token count |

`--actual-tokens` is only ever a number **you** read from the host. The tool will
not derive it.

### One library, several agents

Different agents keep their skills in different directories. Aletheia knows where
each of the supported hosts puts them, so a skill installed under *any* of them
stays reachable:

```text
~/.workbuddy/skills            ~/.hermes/skills            ~/.openclaw/skills
~/.workbuddy/plugins/cache     ~/.claude/skills            ~/.agents/skills
~/.copilot/skills              ~/.kimi/skills              ~/.qwen/skills
~/.gemini/skills               ~/.factory/skills           ~/.kiro/skills
~/.aider/skills                ~/.local/share/crush/skills
~/.opencode/skills             ~/.config/opencode/skills
~/.pi/agent/skills             ~/.qwenworkcn/skills
~/.qwenworkcn/bin/computer-use/skills
```

Doubao Work keeps its skills in the Electron app-data tree instead of a plain
per-host skills directory; all three OS spellings are listed in the install
section above and the registry resolves only the one that can exist on the
machine it runs on (`os.name` decides).

Crush reads two different paths depending on scope: `~/.local/share/crush/skills`
at user level, `.crush/skills` inside a project. Both are listed above and in the
host table, because installing to the wrong one leaves Crush unable to see the
skill at all.

This matters more than it sounds. A library mirrored across agents accumulates
duplicates and drifts, and the audit says so rather than hiding it:

```bash
python skills/aletheia/scripts/router.py audit \
  --root ~/.hermes/skills --root ~/.openclaw/skills --unused-days 30
```

```text
scanned 213 skill(s)
healthy 210   broken 3 (blocking 0)   stale 2   duplicated 17
```

Inventory de-duplicates by name, so a quoted number never points at an ambiguous
pair — but the *count* of duplicate installs is reported honestly, because that
is the thing worth acting on.

Records stay local in `~/.aletheia/ledger.jsonl`. `report` exports a
self-contained HTML file — no CDN, no fonts, no network — where measured values
are badged, estimates carry an `est` marker, and unavailable cells say so in
words. See [`docs/sample-report.html`](docs/sample-report.html).

### Delivering a report when there is no URL

A report that cannot be published as a link is a delivery problem, not a reason
to ship something unreadable. The same data renders three ways:

```bash
python skills/aletheia/scripts/router.py report --out report.html   # file, opens offline
python skills/aletheia/scripts/router.py report --out report.md     # issue / PR / doc
python skills/aletheia/scripts/router.py report --format text       # chat or terminal
```

The format follows `--format`, then the output extension, then HTML. With no
`--out` the report prints to stdout, ready to paste.

The text tier is a **formatted document, not a dump**: heading rules, columns
that stay aligned even with Chinese content (a CJK glyph occupies two terminal
cells), a provenance legend, and every figure labelled with its unit. Bare
numbers in a chat bubble are not offered as a mode.

## Measuring without asking the host

Reading what a host chooses to export is reactive. `estimate` inverts it — walk
the machine, measure what is measurable, never ask anyone:

```bash
python skills/aletheia/scripts/router.py estimate --task "quarterly deck"
python skills/aletheia/scripts/router.py estimate --only excel-xlsx,guizang-ppt-skill
```

```text
input 11,365,980 · output 1,978,510 · cache_read 364,126,214 · cache_write 483,380
completeness: partial — 10 host(s) persist no token counter
library: 252 unique skills (708 duplicate installs)
context cost: 44,322 est. tokens of metadata
```

Two figures are named `unavailable` rather than estimated: **host-internal
reasoning tokens** (never written to disk) and **billed cost** (needs a model id
and a price table). No price table is bundled — a stale one silently becomes a
confidently wrong money figure.

Host log growth is reported as **bytes, explicitly not tokens**, and never summed
into a token total.

The scoping saving, measured from the files rather than modelled:

```text
whole library: 44,322 est. tokens of metadata
scoped to 2:       347 est. tokens        — a 99.2% reduction
```

## Knowing when there is an update

```bash
python skills/aletheia/scripts/router.py update          # is this skill current?
python skills/aletheia/scripts/router.py update --scan   # and every other skill?
python skills/aletheia/scripts/router.py update --no-fetch   # offline: local state only
```

```text
local_version 1.9.0 · local_tag v1.9.0 · branch main
latest_tag    v1.9.0 · update_available false
```

When something is newer it tells you what, and stops there:

```text
UPDATE AVAILABLE: v1.9.0 -> v1.10.0
3 commit(s) behind
  45209d4 Fix the Chinese README, a duplicated changelog entry, and stale caches
  ...
```

### It detects. It never applies.

There is no `--apply`, and a test enforces that. **Rewriting a `SKILL.md` that
another agent is mid-read is a bad trade** — the reader gets a half-written file
and you did not ask for that risk. The command hands you the decision:

```bash
git log HEAD..origin/main --oneline    # read what changed, first
git pull --ff-only origin main
python -m unittest discover -s tests   # verify before trusting it
```

### Update detection needs tags, so the repository has them

Comparing versions requires something to compare against. `v1.8.0` through
`v1.9.0` are tagged, and a test fails if the current version is not — a
release-capable repository that cannot detect its own updates is a contradiction.

### Checking every other skill, not just this one

```bash
python skills/aletheia/scripts/router.py versions             # the whole library
python skills/aletheia/scripts/router.py versions --outdated-only
python skills/aletheia/scripts/router.py versions --no-remote  # offline
```

Measured on a real library:

```text
252 unique skills
  2   git            — a real upstream, genuinely comparable
  50  marketplace    — an install record with a version
  42  frontmatter    — a declared version string and nothing else
  158 none           — no version signal at all
```

**One outdated skill was found and is reported:**

```text
huashu-art-motion: 57d67608ab45 -> 2571ee0a9a04
  https://github.com/alchaincyf/huashu-art-motion.git
```

### The three sources support very different claims

| Source | Can detect a newer release? | Can detect local edits? |
| --- | --- | --- |
| Own git repository | **yes** | yes |
| Marketplace record | no — needs the marketplace API | **yes** (content hash) |
| Declared version | no — nowhere to compare against | no |

A marketplace install record carries an `installedContentHash`, so **44 skills
locally edited after installing** were identified. That matters more than it
looks: updating one of those overwrites the local changes, which is exactly the
kind of surprise a butler should prevent.

### Reminders, not automation

`daily_check.py` includes a version section and exits non-zero when any skill is
behind, so the existing 9:10 scheduler surfaces it with no configuration. The
daily report names the skill, the two commits, and the upstream URL.

**It still never updates anything.** Updating a skill that another agent is
mid-read is a bad trade, and a skill with local edits has work that an update
would destroy.

### Most skills have no upstream, and this says so

```bash
python skills/aletheia/scripts/router.py update --scan
```

```text
252 unique skills · 2 with a git upstream · 250 with none recorded
```

That is the honest state of a typical library: a skill dropped into
`~/.agents/skills/` has no record of where it came from, so nothing can check it
for updates. The scan reports the gap instead of guessing a URL. **250 skills
without provenance is a finding, not a bug** — it tells you which ones will
silently go stale.

## Keeping the library healthy

```bash
python skills/aletheia/scripts/router.py audit            # report
python skills/aletheia/scripts/router.py audit --fix      # repair what is provably broken
python scripts/daily_check.py                             # daily, read-only
```

On a real 300-skill library this finds breakage a routing check never would:

```text
Library: 550 scanned · 539 healthy · 11 broken (0 need a human) · 10 stale · 216 duplicated
```

`--fix` repairs an over-long `description`, an `allowed-tools` list, and missing
frontmatter. **It never deletes a skill** — anything it cannot repair safely is
reported for a human decision instead. Stale and duplicated skills are flagged,
not removed: those calls are yours.

`scripts/daily_check.py` runs the same audit plus a telemetry sample, appends to
a rotating local log, and exits non-zero only when a human decision is needed —
so Task Scheduler or cron can alert on it. Scheduling recipes are in
[`references/MEASUREMENT.md`](skills/aletheia/references/MEASUREMENT.md).

## Session scoping

Keep the whole skill library out of a focused task's context:

```bash
# One invocation
python skills/aletheia/scripts/router.py route "make a deck" --root skills --only slides-design

# Whole session — drop aletheia-session.json in the project root
{ "only": ["slides-design", "image-creation"] }
```

Scope can come from several sources — `--only`, a session manifest, or
`--profile`. **When more than one is present they are intersected, never
overridden.** Withheld skills
are reported as `suppressed_skills` — never silently dropped. Scoping is a
**routing filter, not a security boundary**.

## Context pressure

```bash
python skills/aletheia/scripts/router.py context \
  --transcripts ~/.workbuddy/workspace/sessions --host workbuddy
```

| Tier | Est. use | Action | Claude Code | Codex | WorkBuddy |
| --- | --- | --- | --- | --- | --- |
| `ok` | <70% | Continue | — | — | — |
| `notice` | 70–85% | Compact first | `/compact` | `/compact` | `/compact` |
| `trim` | 85–100% | Compact now | `/compact` | `/compact` | `/compact` |
| `new_session` | ≥100% | Switch, with a handoff | `/clear` | `/new` | `/new` |

> **Honesty note.** Unless your host exposes real token telemetry, this reports
> `is_measured_context_percentage: false`. The figure is estimated from
> on-disk transcript bytes against an assumed window. Aletheia never presents an
> estimate as a measurement.

Before switching sessions, write a handoff: goal, completed steps, key findings,
open questions, and the exact file paths in play.

## CLI

```bash
# Full registry with numbers, filterable
python skills/aletheia/scripts/router.py inventory --query "pdf" --limit 20

# Who chooses: show, or switch and persist
python skills/aletheia/scripts/router.py mode
python skills/aletheia/scripts/router.py mode --set manual

# Owner-controlled hard-injection hooks: show, silence, narrow
python skills/aletheia/scripts/router.py hook
python skills/aletheia/scripts/router.py hook --set off
python skills/aletheia/scripts/router.py hook --events session-start

# Discover skills in conventional locations
python skills/aletheia/scripts/router.py scan

# Retrieve candidates with reasons
python skills/aletheia/scripts/router.py route "analyze this spreadsheet" --top 5

# Validate frontmatter in a skills tree
python skills/aletheia/scripts/router.py lint --root skills

# Offline retrieval benchmark against bundled fixtures
python skills/aletheia/scripts/router.py eval --root tests/fixtures --cases tests/eval_cases.json

# Session scoping
python skills/aletheia/scripts/router.py route "make a deck" --root skills --only slides-design

# Context pressure
python skills/aletheia/scripts/router.py context --transcripts <dir> --host claude

# Progress bar over a declared step list
python skills/aletheia/scripts/router.py progress "read" "write" "verify" --done 1

# Human-readable views of the same data
python skills/aletheia/scripts/router.py inventory --format text
python skills/aletheia/scripts/router.py route "analyze this spreadsheet" --format text
python skills/aletheia/scripts/router.py telemetry --format text

# Tests
python -m unittest discover -s tests -v
```

Every subcommand prints **JSON on stdout** by default — that is the machine
contract. Four commands also speak plain text for the human holding the
terminal: `inventory --format text` (numbered picker with clipped
descriptions), `route --format text` (score bars and match signals per
candidate; `--ascii` for terminals without box drawing), `hosts --format text`
(capability table: measured vs no token telemetry), and `telemetry --format
text` (usage table with the token total). `report` picks its format
from `--format`, then the output extension. A failure prints `{"error": "..."}`
and exits `2`. Argparse still handles genuine argument-parsing errors (an
unknown subcommand, a missing value) with its own usage message, since those
happen before any command semantics exist.

`route` never executes a discovered skill. The `score` is a hand-tuned ordering
signal — not a probability, not a success rate, and not calibrated. Read the
candidate's `SKILL.md` before deciding.

## Project layout

```text
.
├── skills/aletheia/
│   ├── SKILL.md                   # spec-compliant entry point
│   ├── scripts/router.py          # read-only discovery, scope, lint, eval, context, progress
│   ├── scripts/hook_prompt_submit.py  # owner-controlled hard-injection hook entry point
│   └── references/                # TRANSPARENCY · PROGRESS · BUTLER · MEASUREMENT · ROUTING_POLICY · SECURITY · CONTEXT · EXAMPLES
├── prompts/MASTER_PROMPT.en.md    # full resident prompt (English)
├── prompts/MASTER_PROMPT.zh-CN.md # full resident prompt (Chinese)
├── scripts/install.py             # non-destructive installer
├── scripts/daily_check.py         # daily health check (read-only by default)
├── examples/                      # session scope manifest
├── tests/                         # unit tests, fixtures, bilingual eval cases
├── docs/                          # ARCHITECTURE · EVALUATION · RELEASE_CHECKLIST
└── .github/workflows/ci.yml       # Python 3.10 / 3.12 / 3.13
```

## Design principles

- **Standards, not vendor formats** — plain `SKILL.md` + `references/` + `scripts/`
- **Two-level discovery** — host inventory first, local metadata second
- **Human/agent split** — the CLI improves recall and auditability; the agent owns semantics, authorization and execution
- **Honest telemetry** — estimates are labelled as estimates, always
- **Low context cost** — metadata first, full text only when selected
- **Safe defaults** — one-level scan, symlinks refused, no code execution

## Honest limits

**No ordinary SKILL.md or system prompt can guarantee correct skill invocation
on every request.** Aletheia improves hit rate and auditability, and only if the
target agent can actually reach those skills and tools. The CLI is a read-only
candidate retriever — it does not replace the host's skill API, permissions or
executor. The hook (above) makes the *injection* mechanical — the routing
context is added to every conversation whether the model cooperates or not —
but it still cannot force the model to *obey* what was injected; that gap is
disclosed, not papered over. There is no verified public benchmark for this
yet; the bundled fixtures are a smoke test, not an accuracy claim.

## FAQ

**Why not scan every folder on the machine?**
Full-disk recursion is unsafe, slow, and surfaces skills irrelevant to the
current runtime. Only host-registered, user-specified or conventional
directories are scanned.

**Can it auto-invoke plugin or cloud-only skills?**
Only when the host exposes both the list and a real invocation mechanism. File
scanning does not substitute for a plugin interface.

**Will `--bootstrap` overwrite my AGENTS.md?**
No. It only upserts its own marked block. Run `--dry-run` first to see exactly
what changes.

**Does a high score mean it's safe to use?**
No. A score is a lexical ordering signal with no probability meaning and no
calibration. Read the candidate's `SKILL.md`, then decide.

## References

- [Agent Skills specification](https://agentskills.io/specification)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [OpenAI API Skills](https://developers.openai.com/api/docs/guides/tools-skills)
- [OpenAI skills examples](https://github.com/openai/skills)

## License

MIT — see [LICENSE](LICENSE).
Contributions welcome: [CONTRIBUTING.md](CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [SECURITY.md](SECURITY.md)

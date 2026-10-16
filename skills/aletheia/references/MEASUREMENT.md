# Measuring cost honestly, and keeping the library healthy

Two subjects, one rule: **never present a number whose provenance you cannot
name.** Every field below is `measured`, `estimated`, or `unavailable` — and the
distinction is visible in the output, not buried in a footnote.

## What can actually be measured

Aletheia ships adapters for twelve mainstream hosts. **Every host returns the
same keys**, so nothing has to branch on which one lacked data — and a host we
cannot read is reported `unavailable`, never `0`.

```bash
python scripts/router.py hosts          # what is supported and what can be read
python scripts/router.py telemetry      # real totals for every host present
python scripts/router.py telemetry --host claude --host kimi
```

| Host | Skill dir | Telemetry | Session location | Usage block |
| --- | --- | --- | --- | --- |
| Claude Code | `.claude/skills` | yes | `~/.claude/projects/**/*.jsonl` | `message.usage` |
| Codex | `.agents/skills` | yes | `~/.codex/**/*.jsonl` | `usage` |
| Kimi Code | `.kimi/skills` | yes | `~/.kimi/sessions/**/wire.jsonl` | `message.payload.token_usage` |
| Qwen Code | `.qwen/skills` | yes | `~/.qwen/projects/**/*.jsonl` | `usageMetadata` |
| Gemini CLI | `.gemini/extensions` | yes | `~/.gemini/tmp/*/chats/*` | `usageMetadata` |
| Copilot CLI | `.copilot/skills` | yes | `~/.copilot/{otel,session-state}` | `usage` / `data.usage` |
| **OpenClaw** | `.openclaw/skills` | SQLite | per-agent SQLite + legacy JSONL | `message.usage` |
| **Hermes** | `.hermes/skills` | SQLite | `~/.hermes/state.db` (`sessions` table) | column-based |
| OpenCode | `.opencode/skills` | partial | JSON message store | `tokens` |
| Droid | `.factory/skills` | yes | `~/.factory/sessions/*.json` | `usage` |
| Kiro | `.kiro/skills` | yes | `~/.kiro/sessions/cli/*.json` | `usage` |
| Crush | `.crush/skills` | yes | `~/.local/share/crush/projects.json` | `usage` / `totals` |
| Aider | `.aider/skills` | if enabled | `~/.aider/**/*.jsonl` | `usage` |
| WorkBuddy | `.workbuddy/skills` | **no** | persists nothing | — |

### SQLite-backed hosts

**OpenClaw and Hermes keep usage in SQLite**, not JSON. Python's `sqlite3` is in
the standard library, so Aletheia reads them directly — **no third-party driver,
no new dependency**. Databases are opened **read-only via URI**, because a
telemetry reader must never mutate or lock a host's store.

The adapter maps column names onto the same canonical buckets:

```python
"sqlite": {
    "path": "~/.hermes", "glob": "state.db", "table": "sessions",
    "columns": {"input": ("input_tokens", "prompt_tokens"), ...},
}
```

If the table or any expected column is missing, the host reports `unavailable`
with the reason — never a zero.

### Multi-agent skill libraries

Hermes and OpenClaw each maintain their **own** `skills/` directory, and in
practice these mirror the WorkBuddy library. That is a real operational fact,
not an edge case: a library shared across agents accumulates duplicates and
drifts. The audit surfaces it:

```text
$ router.py audit --root ~/.hermes/skills --root ~/.openclaw/skills
  scanned 213 skill(s)
  healthy 210   broken 3 (blocking 0)   stale 2   duplicated 17
```

Inventory de-duplicates by name, so a quoted number never points at an ambiguous
pair — but the count of duplicate *installs* is reported honestly, because that
is the thing worth acting on.

### Every host names its fields differently

This is the part that actually matters, and why the adapters exist:

| Host | Cache-read field | Where it hides |
| --- | --- | --- |
| Claude Code | `cache_read_input_tokens` | inside `message.usage` |
| Codex | `cached_tokens` | `input_token_details`, *beside* `usage` |
| Kimi Code | `input_cache_read` | `message.payload.token_usage` |
| Qwen / Gemini | `cachedContentTokenCount` | `usageMetadata` |
| OpenCode | `cache` / `cacheRead` | `tokens` |

An adapter that assumed the Claude layout would have reported **0 for everything
else** — a confident, well-formatted, completely wrong number. The alias table
maps each host onto one canonical shape:

```text
input · output · cache_read · cache_write
```

Measured on this machine:

```text
host                  ok  files  msgs           input      output    cache_read
Claude Code           Y   2      29                58       8,951     2,377,969
Codex                 Y   141    1                180          96            48
Kimi Code             Y   49     3401       8,842,282   1,917,619   359,392,132
Qwen Code             Y   4      106        2,523,460      51,844     2,356,065
Gemini CLI            -   0      -                              unavailable
```

A host with no data reads `unavailable` — **never `0`**. A zero would be a claim,
and it would be wrong.

### Why cache reads are listed separately

Cache reads cost a fraction of fresh input. Blending them into one "total"
would misrepresent cost by an order of magnitude. The report gives raw counts and
leaves pricing to you.

### SQLite-backed hosts

OpenCode and Goose keep usage in SQLite. Aletheia is stdlib-only and does not
ship a database driver, so their adapters read the JSON message store when one
exists and report `unavailable` otherwise. This is a stated limit, not a silent
zero.

## Before and after a task

```bash
# Before: record the routing baseline and what scoping saves
python scripts/router.py measure "export Q3 workbook to PDF" \
  --only excel-xlsx,guizang-ppt-skill --phase before --label "Q3 deck"

# After: add the number you read from the host
python scripts/router.py measure "export Q3 workbook to PDF" \
  --phase after --actual-tokens 18400
```

`--actual-tokens` is only ever a number **you** read from the host. The tool has
no way to obtain it and will not invent one; omitted, it stays `unavailable`.

## What the comparison does and does not claim

Quantified — reproducible, derived from files just read:

```json
"comparison": {
  "without_aletheia":  { "metadata_tokens_est": 33891 },
  "with_aletheia_scoped": { "metadata_tokens_est": 355 },
  "saved_tokens_est": 33536,
  "saved_percent": 99.0
}
```

Refused — listed with the reason, because guessing would be fabrication:

| Claim | Value | Why not |
| --- | --- | --- |
| Tokens saved by not redoing the wrong skill | `unavailable` | Needs a real A/B run on the same task |
| Actual host usage with vs without | `unavailable` | No telemetry on this host |
| Money saved | `unavailable` | Needs a price and a measured billable count |

Only the metadata saving is measurable from a single run. Everything else needs
two runs and the host's own numbers — and saying so is more useful than a
confident guess.

## Local ledger and report

Records append to `~/.aletheia/ledger.jsonl` — **on this machine, never
uploaded**. A truncated line is skipped rather than breaking the report.

## Delivering a report: three tiers

A report often cannot be published as a URL. That is a delivery problem, not a
reason to ship something unreadable, so the same data renders three ways:

```bash
# 1 · File (default) — a self-contained page, opens anywhere, offline
python scripts/router.py report --out report.html

# 2 · Markdown — for pasting into an issue, doc or PR
python scripts/router.py report --out report.md

# 3 · Plain text — for a chat message or a terminal
python scripts/router.py report --format text
```

The format follows `--format`, then the output extension (`.html` / `.md` /
`.txt`), then HTML as the default. With no `--out`, the report is printed to
stdout — which is the point of the text tier: you paste it and it still reads
as a document.

**The text tier is still a formatted document**, not a dump: heading rules,
aligned columns, a provenance legend, and every figure labelled measured,
estimated or unavailable. Degrading to a bare list of numbers would be a
downgrade the reader can feel, so it is not offered as a mode.

### HTML is always self-contained

No CDN, no web fonts, no scripts, no network calls of any kind. A report that
needs the network to render is a report that fails exactly when it matters — on
an offline machine, in an archived attachment, or behind a corporate proxy. A
test asserts this, so it cannot regress.

## Library health: breakage, staleness, redundancy

```bash
python scripts/router.py audit                      # report
python scripts/router.py audit --fix                # repair what is provably broken
python scripts/router.py audit --unused-days 30     # tighter staleness
```

On a real 300-skill library this reports things worth knowing:

```text
Library: 550 scanned · 539 healthy · 11 broken (0 need a human) · 10 stale · 216 duplicated
```

### What `--fix` will and will not do

| Repairable, fixed automatically | Needs a human |
| --- | --- |
| `description` over the 1024-char spec limit (truncated, and it says so) | Unclosed frontmatter |
| `allowed-tools` written as a YAML list (converted to the spec's string) | Frontmatter that is not a mapping |
| Missing frontmatter entirely (synthesised from the folder name) | A skill whose directory name cannot be a valid name |

**It never deletes a skill.** Losing someone's work to a bot's housekeeping is
unforgivable; a rewritten frontmatter is recoverable and auditable. Files that
cannot be repaired safely are reported instead.

### Stale and duplicated are flagged, not removed

A skill untouched for 90 days still costs metadata every turn — but *you* decide
whether to keep it. Duplicates are common and sometimes intentional (two
versions side by side), so the audit tells you where they are and stops.

## Daily check

```bash
python scripts/daily_check.py              # report only
python scripts/daily_check.py --fix        # also apply safe repairs
python scripts/daily_check.py --quiet      # silent unless something needs attention
python scripts/daily_check.py --notify     # summary ready to paste
```

Appends to `~/.aletheia/daily-check.log` (rotated at 400 lines) and exits `1`
only when a human decision is required — so a scheduler can alert on it.

### Scheduling it

Windows Task Scheduler:

```powershell
$action  = New-ScheduledTaskAction -Execute "python" `
  -Argument "C:\path\to\aletheia\scripts\daily_check.py --notify" `
  -WorkingDirectory "C:\path\to\aletheia"
$trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
Register-ScheduledTask -TaskName "Aletheia daily check" -Action $action -Trigger $trigger
```

macOS / Linux cron:

```cron
0 9 * * * cd /path/to/aletheia && python3 scripts/daily_check.py --notify >> ~/.aletheia/daily.log 2>&1
```

Run it **read-only** first (`--quiet`, no `--fix`) for a few days. Automatic
repair of third-party skill files should be something you watch happen before
you let it run unattended.

## Supporting a host that is not registered yet

Adding one is a data change, not a code change. Append an entry to
`TELEMETRY_HOSTS` in `scripts/router.py`:

```python
"yourhost": {
    "label": "Your Host",
    "sessions": "~/.yourhost/sessions",      # None = no telemetry
    "globs": ("**/*.jsonl",),                  # several layouts are fine
    "usage_paths": (("usage",), ("message", "usage")),
    "aliases": {                               # map its names onto ours
        "input": ("prompt_tokens", "input_tokens"),
        "output": ("completion_tokens", "output_tokens"),
        "cache_read": ("cached_tokens",),
        "cache_write": (),
    },
    "skills": ("~/.yourhost/skills",),         # so the butler can see them
    "native_skill_dir": ".yourhost/skills",
},
```

Then verify against real data before trusting it:

```bash
python scripts/router.py telemetry --host yourhost
```

Two tests guard the registry automatically: every alias must be reachable by the
line prefilter (or its data would be dropped before parsing), and every host must
return the identical key set. Run `python -m unittest discover -s tests` after
adding one.

## The honesty rules, collected

1. No number without a named provenance.
2. No telemetry means `unavailable`, not `0`.
3. Estimates are labelled `estimated` and show their basis.
4. An ETA is never invented; a context percentage is never faked.
5. Savings claims that need an A/B run are refused, with the reason given.
6. `--actual-tokens` is supplied by the human, never derived.
7. Nothing is deleted automatically — ever.

## Running on Windows, macOS and Linux

Aletheia is standard-library only, so there is nothing to install on any of the
three. The differences that do exist are handled explicitly rather than assumed:

| Concern | Windows | macOS / Linux |
| --- | --- | --- |
| Line endings | CRLF preserved on repair | LF preserved on repair |
| Path separators | both `\` and `/` accepted | both accepted |
| Config home | `%USERPROFILE%` via `Path.home()` | `$HOME` |
| sqlite lock semantics | connections closed before teardown | advisory locks |
| Terminal glyphs | ASCII bar fallback | box-drawing bar |

Two of these were real bugs, found by CI rather than by review:

- **CRLF was silently lost on repair.** Python's text mode translates CRLF to LF
  when reading, which made every comparison CRLF-safe but also *erased the
  evidence* of which convention the file used. Every repaired file came back as
  LF — showing as a whole-file diff on Windows. Now the original convention is
  read from the bytes on disk and preserved.
- **The no-dependency path disagreed with the PyYAML path.** Locally PyYAML is
  present, so `diagnose_skill` reached a different verdict than it would without
  it — meaning a skill could pass on a developer machine and fail only on CI.
  Both paths must now agree, and `tests/zero_dependency_check.py` proves it.

### Why this matters beyond tidiness

A feature that works only on the machine where it was written is not a feature.
The zero-dependency guarantee is load-bearing: it is what lets Aletheia run in a
fresh CI container, inside another agent's sandbox, or on a host with no package
manager — which is exactly where a routing tool is most useful.

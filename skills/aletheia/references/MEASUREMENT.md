# Measuring cost honestly, and keeping the library healthy

Two subjects, one rule: **never present a number whose provenance you cannot
name.** Every field below is `measured`, `estimated`, or `unavailable` — and the
distinction is visible in the output, not buried in a footnote.

## What can actually be measured

| Host | Token telemetry | Source |
| --- | --- | --- |
| Claude Code | **yes** | `~/.claude/projects/**/*.jsonl`, `message.usage` |
| Codex | **yes** | `~/.codex/**/*.jsonl`, top-level `usage` |
| WorkBuddy | **no** | nothing persisted; read its own UI |

```bash
python scripts/router.py telemetry
```

Reads every host that persists usage and reports real totals:

```json
"claude": {
  "available": true,
  "messages_with_usage": 29,
  "input_tokens": 58,
  "output_tokens": 8951,
  "cache_read_tokens": 2377969,
  "cache_write_tokens": 483380,
  "billable_tokens_excluding_cache_read": 492389,
  "provenance": "read directly from host session files"
},
"workbuddy": {
  "available": false,
  "input_tokens": "unavailable",
  "reason": "this host does not persist token usage to disk; read it from its own UI"
}
```

A host with no data reads `unavailable` — **never `0`**. A zero would be a claim,
and it would be wrong.

### Why cache reads are listed separately

Cache reads cost a fraction of fresh input. Blending them into one "total"
would misrepresent cost by an order of magnitude. The report gives raw counts and
leaves pricing to you.

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

```bash
python scripts/router.py report --out docs/sample-report.html
```

The HTML is self-contained: no CDN, no fonts, no network. Measured figures are
badged green, estimates carry an `est` superscript, and unavailable cells say so
in words. See `docs/sample-report.html` for a generated example.

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

## The honesty rules, collected

1. No number without a named provenance.
2. No telemetry means `unavailable`, not `0`.
3. Estimates are labelled `estimated` and show their basis.
4. An ETA is never invented; a context percentage is never faked.
5. Savings claims that need an A/B run are refused, with the reason given.
6. `--actual-tokens` is supplied by the human, never derived.
7. Nothing is deleted automatically — ever.

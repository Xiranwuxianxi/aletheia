# Aletheia routing cost report

_Generated 2026-10-18 12:39 UTC · 3 record(s) · local ledger_

## How to read the numbers

| Marking | Meaning |
| --- | --- |
| `measured` | read directly from host session files on this machine |
| `est` | estimated from measured characters via a documented bytes-per-token constant |
| `unavailable` | the host exposes no such figure; deliberately left blank |
| unit | every figure is a count of **tokens** |
| `tokens` | input + output + cache write — cache reads are excluded and counted apart |

## Headline

| Metric | Value | Basis |
| --- | ---: | --- |
| Metadata tokens, no routing | 33,891 | estimated |
| Metadata tokens, scoped | 355 | estimated |
| Reduction | 33,536 (99.0%) | estimated |
| Actual host tokens | see per-host table below | measured where the host logs it |

## Actual host usage, read from session files

| Host | Status | Input | Output | Cache read | Cache write | Tokens | Messages |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Claude Code | **measured** | 58 | 8,951 | 2,377,969 | 483,380 | 492,389 | 29 |
| Codex | **measured** | 180 | 96 | 48 | 0 | 276 | 1 |
| Kimi Code | **measured** | 8,842,282 | 1,917,619 | 359,392,132 | 0 | 10,759,901 | 3,401 |
| Qwen Code | **measured** | 2,523,460 | 51,844 | 2,356,065 | 0 | 2,575,304 | 106 |
| Gemini CLI | **unavailable** | — | — | — | — | — | — |
| ↳ reason | session directory not found on this machine | | | | | | |
| GitHub Copilot CLI | **unavailable** | — | — | — | — | — | — |
| ↳ reason | session directory not found on this machine | | | | | | |
| OpenCode | **unavailable** | — | — | — | — | — | — |
| ↳ reason | session directory not found on this machine | | | | | | |
| Factory Droid | **unavailable** | — | — | — | — | — | — |
| ↳ reason | session directory not found on this machine | | | | | | |
| Kiro | **unavailable** | — | — | — | — | — | — |
| ↳ reason | session directory not found on this machine | | | | | | |
| Crush | **unavailable** | — | — | — | — | — | — |
| ↳ reason | session directory not found on this machine | | | | | | |
| Aider | **unavailable** | — | — | — | — | — | — |
| ↳ reason | session directory not found on this machine | | | | | | |
| WorkBuddy | **unavailable** | — | — | — | — | — | — |
| ↳ reason | this host does not persist token usage to disk; read it from its own UI | | | | | | |

_Total tokens across measured hosts: 13,827,870._
_Tokens = input + output + cache write. Cache reads cost a fraction of fresh input, so they are reported apart and never blended into the total._

## Measurements

| Task id | Phase | Label | No routing | Scoped | Actual |
| --- | --- | --- | ---: | ---: | ---: |
| `task-20261015T085435Z` | before | Q3 deck baseline | 33,891 est | 355 est | unavailable |
| `telemetry-20261015T085501Z` | after | host telemetry | n/a | n/a | unavailable |
| `telemetry-20261015T092507Z` | after | host telemetry | n/a | n/a | unavailable |

## Deliberately not quantified

These are refused rather than estimated, because a guess would look like a result:

- **tokens saved by not redoing the wrong skill** — `unavailable`
  Requires a real A/B run on the same task. The CLI cannot know how much work a wrong skill caused, and guessing would be fabrication.
- **actual host token usage with vs without** — `unavailable`
  No token telemetry on this host. Read it from the host's own UI or API response.
- **money saved** — `unavailable`
  Requires a per-token price and a measured token count; neither is available here.

## Getting real numbers

1. Run the same task twice in the host: once normally, once with a scoped allowlist.
2. Read the token usage the host itself reports at the end of each run.
3. Record it with `router.py measure "task" --phase after --actual-tokens <n>`.

---

_Ledger: `~/.aletheia/ledger.jsonl` · nothing leaves this machine · measured ≠ estimated ≠ available_
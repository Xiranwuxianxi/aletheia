# Progress reporting: a bar that cannot lie

A progress bar is the easiest element in an agent UI to turn into a lie. It
drifts, it stalls at 90%, it promises "almost done" for work that then fails.
Aletheia's rule is narrow and strict: **progress is only ever a count of
genuinely finished steps out of a declared total.** Nothing else.

If you cannot enumerate the steps, you do not have a progress bar — you have a
narration. Say what you are doing instead.

## The four states

| State | Bar shows | Means | Never use for |
| --- | --- | --- | --- |
| `working` | Filled to the current step, `N/total` | Steps are advancing right now | A step you have merely *started* |
| `blocked` | Filled to the stall point | **Waiting for a human decision** | A failure |
| `failed` | Filled to where it stopped | The task cannot proceed | A transient hiccup you will retry |
| `done` | Full, `✓ N/total` | Every step finished **and verified** | "It probably worked" |

`blocked` and `failed` are separate on purpose. Waiting for a human at a
confirmation gate is a healthy pause. Rendering it as an error trains people to
panic-click, and rendering it as merely "working" hides that nothing is moving.

## Rules

1. **Declare before you start.** List the steps up front so the denominator is
   visible and cannot drift.
2. **Only count finished steps.** A step in progress does not advance the bar.
3. **Never invent an ETA.** There is deliberately no time field. An agent cannot
   know how long the next step takes, and a wrong ETA is worse than none — the
   same honesty rule that governs context percentages.
4. **100% means verified.** Not "written", not "looks right" — checked.
5. **Never move the bar backwards** to make a failure look smaller. If a step is
   undone, add a step and say so.
6. **Update at boundaries, not per message.** Advance on stage transitions:
   after reading instructions, after a gate clears, after verification. A bar
   that flickers every sentence is noise.
7. **Omit the bar for small tasks.** A one-line answer does not need 0%.

## Format

```text
[████████████░░░░░░░░░░░░]  50%  2/4  → writing report
```

Full machine-readable form, which also lists each step's status:

```bash
python scripts/router.py progress \
  "gather sources" "read SKILL.md" "write report" "verify output" \
  --done 2 --current "writing report"
```

```json
{
  "state": "working",
  "percent": 50,
  "completed": 2,
  "total": 4,
  "eta": null,
  "eta_note": "No time estimate is available; an agent cannot know how long the next step takes.",
  "countable": true,
  "steps": [
    {"step": "gather sources",   "status": "done"},
    {"step": "read SKILL.md",    "status": "done"},
    {"step": "write report",     "status": "current"},
    {"step": "verify output",    "status": "pending"}
  ]
}
```

Gate and failure states:

```bash
# Waiting on the user — bar stops at the gate, does not read as an error
python scripts/router.py progress "gather" "read" "overwrite report.pdf" "verify" \
  --done 2 --state blocked --note "overwrite Q3.pdf, or write v2 alongside?"

# Genuinely stuck
python scripts/router.py progress "gather" "extract" "build" --done 1 \
  --state failed --current "pdftotext exited 1"
```

Use `--ascii` for terminals without box-drawing characters.

## Anti-patterns

| Anti-pattern | Why it fails |
| --- | --- |
| "Making progress… 90%!" with no step list | The 90% is a vibe, not a count |
| Bar jumping 20% → 95% in one update | The denominator was never real |
| ETA like "about 2 minutes left" | Unfounded; wrong ETAs destroy trust faster than no ETA |
| `failed` styling for a confirmation gate | Trains panic-clicking |
| Reaching 100% after writing but before verifying | 100% must mean checked |
| Bar that resets to 0% on a retry | Hides the stall instead of explaining it |
| A bar on every reply of a two-line answer | Ceremony, not transparency |

## Relation to the five-stage trace

Progress answers *how far along*; the trace in `TRANSPARENCY.md` answers *what
happened*. They are complementary: the bar is a glanceable summary, the trace is
the auditable record. When a bar shows `blocked`, the trace is where the user
reads the actual options.

Progress never replaces the verdict. A bar at 100% with no evidence line is an
unverified claim wearing a nicer outfit.

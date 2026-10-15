# Transparency protocol: making execution supervisable

Aletheia means *unconcealment*. This file defines what must be visible, in what
order, and where the agent must stop and ask. The goal is not verbose output —
it is an auditable trail where a reader can reconstruct what happened, what was
chosen, what was actually executed, and what evidence supports the result.

## The five-stage disclosure

For any task where skill selection or tool use is non-trivial, disclose these
stages. Compress them into prose for trivial tasks; expand them when the user
asks what you are doing, when auditing, or when the trace matters.

| Stage | Must state | Evidence required |
| --- | --- | --- |
| 1. Intent | The actual deliverable and its format, separated from the topic mentioned in passing | Restate the request in one line; name the artifact type |
| 2. Candidates | Which skills were considered, including ones **rejected** and why | A real read of each considered `SKILL.md` |
| 3. Decision | The chosen skill(s), or a deliberate decision to use none | Scope/tool fit, not keyword overlap |
| 4. Operations | Every tool call, command, file write and network action, in order | Actual tool IDs, paths, exit status |
| 5. Verdict | What was produced, how it was checked, what remains unverified | Validation actually performed, not intended |

### Why rejected candidates are mandatory

Showing only the selected skill hides the most useful signal: whether a better
option was silently passed over. Naming a rejected candidate with the reason
("wrong artifact type", "requires a tool this host does not expose") lets the
user correct a wrong turn before it costs work.

## Progress alongside the trace

The trace records *what happened*; a progress bar summarises *how far along* it
is. For multi-step tasks show one, anchored to the same five stages. Progress is
only ever a count of genuinely finished steps out of a declared total — never an
extrapolation, and never an ETA, which an agent cannot support. When the bar is
`blocked`, the user reads the actual options in the gate message here. See
`PROGRESS.md`.

## Disclosure format

Prefer this compact shape. Keep each line to one fact.

```text
Tracing: <one-line task restatement>
Skills considered: <name> (selected | rejected — <reason>)
Operations:
  1. <tool> <target> — <result, exit status or error>
  2. ...
Evidence: <what was checked, and its actual outcome>
Not verified: <anything claimed or assumed but not checked>
```

Rules:

- **No theatrical reasoning.** Do not narrate a hidden chain-of-thought. Disclose
  the decision-relevant facts: what you concluded, what you rejected, what you
  are about to do. A confident, short, checkable trace beats a verbose internal
  monologue.
- **Never announce an intent and proceed.** If you state you will use skill X,
  either read X before acting, or say plainly that you have not yet.
- **Report failures as they happen.** A trace that hides a failed step and only
  shows the successes is worse than no trace.
- **Redact secrets.** Show paths and tool names; redact tokens, keys and
  personal data. Traces get pasted into issues and chat logs.

## Stop gates: when to ask before acting

Never treat "continue" as blanket authorization. Ask first when a step is
**irreversible, outward-facing, expensive, or ambiguous**. Present the options
concretely rather than a bare "shall I proceed?".

| Gate class | Examples | Required behavior |
| --- | --- | --- |
| Destructive | overwrite an existing file, delete, drop, force-push | Name the exact target, its size/mtime, and the alternative (write alongside) |
| Outward-facing | send email, publish, post, push to a remote | Show the literal recipient/target and the content that will leave the machine |
| Financial | purchase, paid API, deploy to production | State the cost or blast radius and require explicit confirmation |
| Irreversible side effects | installing packages, changing global config, sending data to a third-party service | List exactly what will change and how to undo it |
| Ambiguous scope | two materially different readings of the request | State both readings and the consequence of each, then ask |

A good gate message is specific and offers the safe default:

```text
This will overwrite Q3-report.pdf (2.1 MB, modified 3 days ago).
  1 · Overwrite in place
  2 · Write Q3-report-v2.pdf and keep both   ← recommended
```

Do not gate on: reading files, searching, running tests, or other reversible
local inspection. Gating everything is its own failure mode — it trains the user
to click through without reading.

## Session scoping: only the skills this task needs

A focused task should not drag the entire installed library into the routing
context. Two mechanisms, both optional:

```bash
# Per-invocation: consider only these skills
python skills/aletheia/scripts/router.py route "make a deck" --root skills --only slides-design

# Per-session: drop an aletheia-session.json next to the project
python skills/aletheia/scripts/router.py route "make a deck" --root skills
```

`aletheia-session.json`:

```json
{
  "only": ["slides-design", "image-creation"],
  "note": "Deck work only. Remove this file to restore full routing."
}
```

`--only` overrides the manifest, and the two intersect when both are present.
Suppressed skills are reported in the output as `suppressed_skills`, never
silently dropped, so the user can see what was withheld. Scoping is a **routing
filter, not a security boundary** — it reduces noise and context cost; it does
not prevent a host-mandated skill from running.

If every suppressed skill is genuinely irrelevant, prefer deleting the
manifest over widening it. A narrow allowlist that you repeatedly edit is a
manifest you should not have created.

## Context pressure and switching sessions

Context is a hard limit; discovering it by hitting it wastes work. Check pressure
at task boundaries, not mid-answer:

```bash
python skills/aletheia/scripts/router.py context --transcripts ~/.workbuddy/workspace/sessions --host workbuddy
```

Tiers and the host-specific command to run:

| Tier | Estimated use | Action | Claude Code | Codex | WorkBuddy |
| --- | --- | --- | --- | --- | --- |
| `ok` | < 70% | Continue | — | — | — |
| `notice` | 70–85% | Compact before the next large task | `/compact` | `/compact` | `/compact` |
| `trim` | 85–100% | Compact now | `/compact` | `/compact` | `/compact` |
| `new_session` | ≥ 100% | Start a new session, carry a summary | `/clear` | `/new` | `/new` |

**Honesty requirement.** Unless the host exposes real token telemetry, this
command reports `is_measured_context_percentage: false`. The number is derived
from on-disk transcript bytes against an assumed window. Present it as an
estimate. Never state a context percentage as if it were measured, and never
invent one when no signal exists — fall back to qualitative evidence (repeated
questions, forgotten constraints, very long transcript) and say that is what you
observed.

Before switching sessions, write a handoff: current goal, completed steps,
key findings, unresolved questions, and the exact file paths in play. Losing
that state is worse than the context limit.

## What transparency does not mean

- Not a wall of text on every reply. Match depth to stakes; trivial answers need
  none of this.
- Not permission to perform the action after announcing it. Stage 1–3 are
  narration; the gate is real.
- Not exposing private system instructions, hidden tool protocols, or other
  agents' internals. Trace *your own* decisions.
- Not a substitute for correct work. A beautiful trace of a wrong plan is still
  a wrong plan.

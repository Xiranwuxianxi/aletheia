---
name: aletheia
description: >-
  Routes an agent's incoming task to appropriate already-installed Agent Skills, makes the
  routing and execution trail visible to the user, reports countable task progress, stops for
  confirmation before irreversible or outward-facing actions, detects overlapping capabilities,
  and verifies that selected SKILL.md instructions are actually read and followed. Use at the
  beginning of any nontrivial task, when choosing among existing skills, when a user asks what
  you are doing or how far along you are, when a skill was unexpectedly skipped, or when
  auditing skill invocation. Supports session-scoped skill allowlists and read-only
  context-pressure checks. Never installs or executes third-party skills automatically.
license: MIT
compatibility: Requires filesystem access for the optional Python 3.10+ discovery helper; skill selection works manually with a host-provided skills list when filesystem or Python is unavailable.
metadata:
  version: "1.7.1"
  category: meta-routing
---

# Aletheia — the skill butler

*Aletheia* (Ἀλήθεια) is the Greek principle of **unconcealment** — truth as that
which is *not hidden*. It is the precise antonym of a black box. This skill
routes tasks to the right installed skills **and shows its work.**

You are a **butler over the whole installed library**: you know what is
installed, you decide who chooses, and you show your reasoning either way.


## Purpose

You are a **skill selection coordinator** that operates in the open. For each
meaningful task: identify the real deliverable, surface the candidate skills,
decide and justify, execute, and verify — while keeping the user able to see
each step and interrupt before anything irreversible happens. A matched filename
is not evidence of invocation. An announced action is not a performed action.

## Who chooses: two modes

The owner picks the mode **once**, at install time (`install.py --mode auto|manual`).
It then persists; switching later takes one sentence.

| Mode | Behaviour |
| --- | --- |
| `auto` (default) | You choose, then disclose what you picked, what you rejected, and why |
| `manual` | You present numbered candidates and wait for the owner to answer |

Either way the five-stage disclosure below still applies — manual mode replaces
*who decides*, not *what must be visible*.

Switch on request, without ceremony:

- "你来选" / "you decide" / "switch to auto" → `auto`
- "我自己选" / "let me choose" / "switch to manual" → `manual`
- "换个状态" / "change mode" → show the current mode and both options

State lives in `aletheia-config.json`:

```bash
python scripts/router.py mode                       # show
python scripts/router.py mode --set manual          # owner takes over
python scripts/router.py mode --set auto            # hand it back
```

**In manual mode, offer numbers — not a wall of names:**

```bash
python scripts/router.py inventory --query "quarterly deck" --limit 12
```

```text
Which skills should I use? Reply with a number, several (2,5), 'all', or 'none'.

 1. guizang-ppt-skill   editable PPTX generation
 2. excel-xlsx         spreadsheet read/write
 3. baoyu-slide-deck   image-rich slide decks
 4. academic-writing    paper structure and citations
```

Accept `3`, `2 5`, `2,5`, `all`, and `none` (meaning: no skill — just do the
task directly). Numbers are **per-invocation**; if the library changes, list
again rather than reusing stale numbers. With hundreds of skills installed,
always `--query` first instead of dumping the whole registry.

## Mandatory preflight (every incoming task)

1. **Parse the intent**: distinguish task objective, required output format, domain, tools, constraints, safety and authorization. For follow-ups, inherit unchanged prior constraints.
2. **Identify available capabilities**: first read host-exposed installed skill metadata or skill-list tools. When local filesystem is accessible, retrieve additional candidates via `scripts/router.py`. Never assume that the CLI can enumerate remote, plugin-only or host-managed skills.
3. **Select, or consciously decline**: weigh actual task fit against name, description, required tools, data access and dependencies. Use zero skills for a trivial request without a relevant skill. If multiple skills apply, use a primary skill plus genuinely necessary supporting skills, and sequence them by dependency.
4. **Activate before execution**: open the complete `SKILL.md` of each selected skill using the host's skill reader (when available) or filesystem read, and only then read task-relevant references. Comply with higher-priority instructions and user approval boundaries. Do not say "used Skill X" unless it was in fact read and applied to execution.
5. **Execute + verify**: follow the activated workflow, use actual permitted tools, validate the deliverable and accurately report what happened. When inaccessible, briefly identify what is missing; use a safe equivalent only if it satisfies the user goal.

## Transparency: show the trail

For any non-trivial task, disclose five stages — compress for casual replies,
expand when auditing or when the user asks what you are doing:

| Stage | Must state |
| --- | --- |
| Intent | The real deliverable and its format, separated from the topic mentioned in passing |
| Candidates | Skills considered, **including rejected ones and why** |
| Decision | Chosen skill(s), or a deliberate choice of none |
| Operations | Every tool call, command, write and network action, in order |
| Verdict | What was produced, how it was checked, what is still unverified |

Use this compact shape:

```text
Tracing: <one-line task restatement>
Skills considered: <name> (selected | rejected — <reason>)
Operations:
  1. <tool> <target> — <result>
Evidence: <what was checked and its actual outcome>
Not verified: <anything assumed but unchecked>
```

Disclose decision-relevant facts, not a theatrical internal monologue. Report
failures when they happen. Never announce an intent and then proceed as if it
were done. Redact secrets from anything you display.

## Stop gates

Never treat "continue" as blanket authorization. **Stop and ask** before
irreversible, outward-facing, financial or ambiguous steps. Name the exact target
and offer the safe default:

```text
This will overwrite Q3-report.pdf (2.1 MB, modified 3 days ago).
  1 · Overwrite in place
  2 · Write Q3-report-v2.pdf and keep both   ← recommended
```

Do **not** gate on reading files, searching, running tests or other reversible
local inspection — over-gating trains users to approve without reading. Full gate
table and rationale: `references/TRANSPARENCY.md`.

## Progress reporting

For multi-step tasks, show a progress bar so the user can see movement without
reading every message.

```bash
python scripts/router.py progress \
  "gather sources" "read SKILL.md" "write report" "verify output" \
  --done 2 --current "writing report"
# [████████████░░░░░░░░░░░░]  50%  2/4  → writing report
```

**Progress is only ever a count of finished steps out of a declared total** —
never a vibe, never an extrapolation. Four states: `working`, `failed`, `done`,
and `blocked` — which means *waiting on a human decision*, not an error.

Three rules carry the weight: **never invent an ETA** (there is no time field; a
wrong ETA is worse than none), 100% means *verified*, and small tasks get no bar
at all. Everything else — thresholds, update cadence, anti-patterns — is in
`references/PROGRESS.md`.

## Candidate discovery (when the script and local folders exist)

```bash
python scripts/router.py scan --json
python scripts/router.py route "Convert a PDF into a concise report" --top 5
python scripts/router.py route "分析Excel并生成图表" --root /workspace/.agents/skills
```

The Python helper reads *only local SKILL.md metadata* and returns approximate candidates, not a decision, execution, or proof. Consider its signals advisory. If you are not in this skill directory, use the absolute path to `scripts/router.py`. It never installs, runs, imports, or trusts candidate skill code. To audit metadata, use `python scripts/router.py lint --root <skills-parent>`.

## Session scoping — only the skills this task needs

Restrict routing to a focused set so the whole library does not enter context:

```bash
# Per invocation
python scripts/router.py route "make a deck" --root skills --only slides-design,image-creation

# Named reusable allowlist from .aletheia/profiles/<name>.json
python scripts/router.py route "make a deck" --profile deck

# Per session: drop aletheia-session.json in the project root
{ "only": ["slides-design", "image-creation"] }
```

`--only` overrides the others; all sources present means intersect. On a
186-skill inventory, scoping to 3 cuts metadata from 58.6 KB to ~1 KB — check
`scope.context_estimate` for your own numbers.

**Check `scope.warning` and `scope.unmatched_allowed`.** A typo, or a skill that
failed metadata lint, otherwise looks exactly like "no relevant skill exists".

Scoping is a **routing filter, not a security boundary**. Suppressed names are
not printed by default (at 186 skills the list costs more than scoping saved) —
use `--scope-detail` to audit. Criteria for choosing what to enable, and how to
verify the switch took effect: `references/SCOPE_CONTROL.md`.

## Context pressure — know when to switch sessions

At task boundaries, check whether the conversation is approaching its limit:

```bash
python scripts/router.py context --transcripts ~/.workbuddy/workspace/sessions --host workbuddy
```

Tiers: `ok` (<70%) continue · `notice` (70–85%) compact · `trim` (85–100%)
compact now · `new_session` (≥100%) switch. Host commands: Claude Code
`/compact` / `/clear` · Codex `/compact` / `/new` · WorkBuddy `/compact` / `/new`.

This command reports `is_measured_context_percentage: false` unless the host
exposes real telemetry — the figure is estimated from on-disk transcript bytes.
Present it as an estimate. **Never state a context percentage you did not
measure.** Write a handoff summary (goal, completed steps, findings, open
questions, file paths) before switching sessions.

## Decision policy

- **Directly named skill**: prioritize it if available and applicable; otherwise transparently explain the mismatch or unavailability.
- **High-confidence, narrow fit**: activate before significant work. **Two different deliverables** (e.g. research plus presentation): chain complementary skills. Avoid summoning every superficially related skill.
- **Tie or overlap**: inspect relevant candidates' `SKILL.md`; pick based on scope, constraints, working tool access, higher-priority requirements, and intended artifact, not keyword score.
- **No eligible skill**: use core capabilities; never hallucinate a skill or block an answer just to enforce routing.
- **A skill requires a missing tool/permission**: it is not executable; find a permitted alternative or disclose the limitation. Do not silently skip required steps.
- **Specialized host rules**: if the runtime mandates a specific built-in skill/tool for a domain, invoke that first; this router never overrides the host.

## Orchestration & context budget

- Keep the coordinator focused on integration and final quality. Where genuine subagents are exposed, assign independent, low-risk discovery/validation/file-organization subtasks in parallel, provide bounded inputs and expected outputs, and verify their results. Otherwise do those subtasks directly; never claim phantom subagents.
- Do not load all full skill files every turn. Discover using metadata, read only chosen SKILL.md and necessary references. Cache a concise task-local inventory only while valid; refresh on skill changes or obvious mismatches.
- Continue troubleshooting meaningful failures with evidence-based alternatives, respecting time, cost, permission and safety limits; stop when continuing would create disproportionate risk or no useful next action.

## Evidence standard

Distinguish explicitly between **discovered**, **selected**, **instructions read**, **tools used**, **deliverable verified** — and show the rejected alternatives. A ranking score is neither a probability nor an invocation record. Mention skill names briefly in the answer only when it assists the user or they request an audit. Never expose private paths, hidden tool protocols, or secrets.

Read further only when required:
- `references/TRANSPARENCY.md` — disclosure format, stop gates, session scoping, context tiers.
- `references/PROGRESS.md` — the four progress states, when to update, anti-patterns.
- `references/SCOPE_CONTROL.md` — choosing which skills to enable, and what that saves.
- `references/BUTLER.md` — the full library inventory, auto/manual modes, numbered selection.
- `references/MEASUREMENT.md` — token telemetry per host, before/after comparison, audits and repairs.
- `references/ROUTING_POLICY.md` — tie breaking, sequential and parallel combinations, edge cases.
- `references/SECURITY.md` — trust, injection, authorization and high-impact operations.
- `references/CONTEXT_AND_SUBAGENTS.md` — token efficiency and delegation.
- `references/EXAMPLES.md` — realistic selection examples.

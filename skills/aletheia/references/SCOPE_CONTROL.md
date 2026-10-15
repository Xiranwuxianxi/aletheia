# Controlling which skills are active, and what that costs

Routing scope answers "which skills may be considered". This file answers the
prior question: **which skills should be switched on for this task, and how much
context does each one cost?**

## Start with the number

On a machine with a large skill library, metadata alone is expensive. Measured on
a 186-skill inventory:

| State | Metadata per turn | Approx. tokens |
| --- | --- | --- |
| Unscoped (all skills visible) | 58.6 KB | ~17,000 |
| Scoped to 3 skills | 0.98 KB | ~280 |
| Scoped to 8 skills | ~2.6 KB | ~740 |

Each unscoped skill costs roughly **315 bytes** of `name` + `description` before
any work begins. That is the price of keeping everything switchable.

Check your own numbers rather than assuming:

```bash
python skills/aletheia/scripts/router.py scan --root ~/.workbuddy/skills --only a,b,c
# scope.context_estimate.saved_percent tells you exactly what scoping bought.
```

## Choosing what to switch on

Turn a skill **on** when the task's deliverable genuinely needs it. Leave it
**off** when it is merely adjacent. Good discriminators:

| Switch ON | Leave OFF |
| --- | --- |
| It owns the artifact you are producing | It could plausibly help but will not be used |
| Its instructions change how you do the work | You already know how to do this step |
| It encodes a tool or format you lack | Another enabled skill covers the same ground |
| The task's success depends on its output quality | It only mentions the same keyword |

Start smaller than feels right. A focused allowlist of 3 is easier to reason
about than 12, and widening is one edit away.

## The three levels

```bash
# 1 · Narrowest — one invocation, nothing persisted
python skills/aletheia/scripts/router.py route "task" --only skill-a,skill-b

# 2 · Session — persist for the project, still easy to delete
#    aletheia-session.json  { "only": ["skill-a", "skill-b"] }

# 3 · Task profile — a named preset for a recurring kind of work
python skills/aletheia/scripts/router.py route "task" --profile deck
```

A profile is just a reusable allowlist, so a recurring workflow does not need its
allowlist retyped. Keep them small and honest; a profile that enables 40 skills
is not a profile.

## Verify the switch actually took effect

The most common failure is a **silent miss**: a typo, or a skill that failed
metadata lint and is therefore invisible to the router. Both look identical to
"no relevant skill exists". Aletheia reports this explicitly:

```json
"scope": {
  "visible": 0,
  "suppressed_count": 186,
  "unmatched_allowed": ["docx", "xlsx", "pptx"],
  "warning": "3 allowed skill(s) matched nothing — check spelling, or whether the skill failed metadata lint..."
}
```

If `visible` is 0 and `unmatched_allowed` is non-empty, the scope did not do what
you meant. Check real names first:

```bash
python skills/aletheia/scripts/router.py scan --root ~/.workbuddy/skills \
  | grep -o '"name": "[^"]*"' | grep -i ppt
```

Real example from this repository's own testing: `--only docx,xlsx,pptx` matched
**nothing**, because the installed names were `excel-xlsx`, `guizang-ppt-skill`
and `baoyu-slide-deck`.

## Scope is not a security boundary

Scoping filters **routing**. It does not prevent execution: a host-mandated skill
still runs, and an agent that decides to read a suppressed `SKILL.md` still can.
Use host-level permission controls for enforcement; use scope to save context and
reduce noise.

Suppressed names are **not** printed by default — at 186 skills the name list
costs more context than scoping saved. Pass `--scope-detail` when you actually
need to audit what was withheld.

## When to widen instead

Widen deliberately, not by reflex:

- The task changed shape mid-session — add the new skill, keep the rest off.
- Routing kept returning `no_match` while you knew a relevant skill existed.
- A composite task needs a second domain (research, then slides).

Narrow to one task's actual shape, and reset when the task ends. An allowlist
edited upward forever stops being a scope and becomes an accident.

## Relationship to context pressure

Scoping reduces the **baseline**; compaction handles a **full** context. They
solve different problems and compose:

```bash
# Baseline is too fat — narrow before starting
python skills/aletheia/scripts/router.py route "task" --only a,b,c

# Context is already full — check and hand off
python skills/aletheia/scripts/router.py context --transcripts <dir> --host workbuddy
```

See `CONTEXT_AND_SUBAGENTS.md` for tiers and host commands, and
`TRANSPARENCY.md` for how scope and the execution trace fit together.

# Context-efficient routing & delegation

## One fast check per task, not a full investigation per message

Every task gets a mental preflight; only run discovery tools if skill use could materially change the method or result, the user explicitly requests a skill, the available list changed, or there is routing uncertainty. For casual questions, answer normally. When a known, host-mandated skill exists, use it directly without a redundant second routing scan.

## Progressive loading

At the beginning of a session, load/retain names and descriptions where available, not every SKILL.md. On task arrival, pick at most 3–5 plausible candidates to examine, then load the chosen skill(s). Read reference files selectively. Save an internal short summary of requirements and output status across long tasks; do not paste raw tool outputs into every subagent handoff.

## Subagent delegation (only when host truly supports it)

Delegate bounded and independently checkable tasks: search for citations, compare two skill manifests, collect a file inventory, run controlled tests, or validate output. Give a clear deliverable, allowed tools, time/budget bounds, and a request to report uncertainties. Keep main-agent responsibility for routing decisions, conflicting evidence, high-impact authorization and final acceptance tests. Do not spawn subagents to restate the entire conversation.

## Honest context health

Use measured context-window capacity or token telemetry only when the host exposes it. An illustrative policy is informational notice at 70%, summarize and trim around 85%, consider new session at 95%; these are **not** estimates. Without telemetry, warn only on qualitative evidence of context degradation, e.g. sustained repetition, dropped constraints, or extremely long transcript, and clearly say there is no measured percentage. Avoid alert spam.

## Verification budget

Spend effort proportional to failure impact: brief answer -> factual check; edited file -> diff/checksum; code -> tests and lint; data -> integrity and calculation checks; deployment/production -> permissions, rollback plan, observable verification. Do not inflate tool calls merely to make the process look thorough.

# Evaluation: distinguish retrieval, invocation, and task completion

A skill-router should not be judged by whether it prints plausible names. Evaluate **three** separate objectives.

## 1. Candidate retrieval

Use `python skills/aletheia/scripts/router.py eval --root tests/fixtures --cases tests/eval_cases.json`.

Each case has `task` and an acceptable `expect` list. An empty list is an intentional no-skill case. The script reports expected-hit in top 3 and no-match behavior. The fixture suite is a **smoke test**, not a universal accuracy benchmark. The default score threshold is a tunable heuristic. Add representative user intents and installed skills to a private test suite before operational use.

Metrics for a larger labeled suite: Recall@3, Precision@1, false-positive rate on no-skill tasks, ambiguous-case coverage, and performance by language/output modality. Report the number and origin of examples. Explicitly track changes as Skills are added/removed.

## 2. Actual invocation (requires runtime telemetry)

Collect **host-observed** evidence, not an LLM statement such as “used skill x”:

1. `skill_inventory_seen`: time and list/version of available skills.
2. `skill_selected`: task trace ID, selected skill identifier/version and reason (redacted).
3. `skill_read`: confirmed read of the selected SKILL.md, with path or host ID.
4. `tool_invoked`: actual relevant tool/call ID and result, where applicable.
5. `deliverable_validated`: artifact existence and task-specific checks.

Useful metrics: relevant-skill invocation rate, wrong-skill invocation rate, skip rate, unauthorized action rate, duplicate invocation rate, tool failure recovery, and wasted tokens/time. A selected skill without a real read is *not* a successful activation. A loaded skill without meaningful execution is *not* a completed task.

## 3. Quality of deliverable

Compare with and without the router on a balanced evaluation set. Keep task difficulty, model, tool privileges and contexts comparable. Grade: correctness, constraint satisfaction, artifact quality, citation fidelity, runtime failures, cost, latency and safety. A slower router with no quality lift is not automatically better.

## Scenario categories to add

- Explicit skill names, aliases, bilingual instructions and misspellings.
- Multiple suitable skills; two-stage cross-format deliverables; conflicting scope.
- Tool-only/cloud-managed Skills invisible to local scanning.
- Unavailable, revoked or broken skill dependencies.
- Malformed frontmatter, duplicate names, symlink directories and metadata injection.
- Requests with no matching skills and ordinary conversational requests.
- Permission boundaries, destructive actions and secret-bearing prompts.
- Long contexts, skill inventory changes and agent session restarts.

## Improvement loop

Failure -> inspect expected vs actually seen candidates -> decide whether metadata descriptions, alias retrieval, host registry integration, semantic selection, or task execution is at fault -> add a regression case -> apply the smallest fix -> rerun retrieval and real agent execution tests. Never optimize retrieval numbers while ignoring genuine invocation or final quality.

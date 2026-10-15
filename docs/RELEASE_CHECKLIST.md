# Release quality checklist (v1.1.0)

## Content and standards

- [x] Canonical standard-compliant `skills/aletheia/SKILL.md` with YAML name/description, optional metadata and references.
- [x] Portable standalone skill includes LICENSE, CLI and all references.
- [x] Bilingual resident prompts (`prompts/MASTER_PROMPT.en.md` + `.zh-CN.md`).
- [x] Bilingual README with a language switcher, English as the default entry.
- [x] Transparency protocol documents the five disclosure stages and gate taxonomy.
- [x] Python standard-library fallback works when PyYAML is not installed.
- [x] Repository uses a standard open-source root layout (README ×2, LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, .github, docs, prompts, examples, tests).
- [x] No duplicated skill copies or release archives committed to the tree.

## Verification

- [x] Installer default refusal on conflicting files; `--force` backup, idempotence, dry-run and preservation of existing root instructions covered by tests.
- [x] Scanner does not execute skill code or use a network API.
- [x] Session scoping filters candidates and reports suppressed skills rather than hiding them.
- [x] Context pressure is explicitly labelled an estimate; no measured percentage is ever fabricated.
- [x] Bilingual and multi-skill retrieval smoke tests, no-skill cases.
- [x] GitHub CI, licensing, security/contribution/architecture/evaluation docs.
- [x] Version number is consistent across `pyproject.toml`, `SKILL.md` and `CHANGELOG.md` (enforced by a unit test).

## Honestly not verified

- [ ] Live host integration benchmarks for a real Claude Code and Codex installation — **not performed in this container**, require a host environment and installed skills.
- [ ] Independent security audit and comprehensive adversarial evaluation — **not performed**.
- [ ] Usability study of the disclosure format with real users — the five-stage layout is a reasoned design, not a validated one. Over-disclosure is a real risk.
- [ ] Context percentages validated against actual host token counters — the byte-based estimate has not been calibrated against a known window.

This is an honest release checklist, not a certification of real-world perfect skill selection.

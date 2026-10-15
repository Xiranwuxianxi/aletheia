# Architecture and host integration

## Control plane vs. execution plane

```text
                    Incoming task
                          |
               Lightweight intent parse
                          |
      +-------------------+--------------------+
      |                                        |
Host-provided skill inventory         Local metadata scan
(host API / plugin tool / etc)    (safe `router.py` SKILL.md only)
      |                                        |
      +--------------------+-------------------+
                           |
                  Candidate shortlist
                           |
                 Agent semantic review
          (scope, format, permissions, conflict)
                           |
            Read real SKILL.md instructions
                           |
                  ---- STOP GATE ----
        irreversible / outward-facing / financial
                  action requires user choice
                           |
             Host-mediated tools/execution
                           |
              Output and evidence checks
                           |
         Trace disclosed: intent · candidates
        (incl. rejected) · decision · operations
                           |
                Honest user delivery
```

**Design constraint:** the script is not an agent runtime, a shell plugin, a package manager, or an executor for discovered skills. It discovers likely matches without granting any further capabilities. A host-native skill read/invocation must perform the actual work. The coordinator is a meta-skill with an AGENTS.md/CLAUDE.md always-on hook because automatic activation of a normal Skill is not guaranteed.

**Why the gate sits where it does:** routing decisions are reversible and cheap to redo, so they proceed without asking. Execution that destroys data, sends content off-machine, spends money, or rests on an ambiguous reading is not reversible, so it stops. Gating the reversible stages instead would train users to approve without reading — see `skills/aletheia/references/TRANSPARENCY.md`.

## Canonical parts

- `skills/aletheia/SKILL.md`: frontmatter for discovery plus authoritative lifecycle instructions. Transparency stages and stop gates lead the document, since an unmonitored run is the failure mode this project exists to prevent.
- `references/`: detailed policies kept outside startup context. Explicit relative references follow progressive disclosure.
- `references/TRANSPARENCY.md`: the disclosure format, gate taxonomy, session scoping and context tiers.
- `scripts/router.py`: one-file, Python 3.10+ metadata tool, stdlib-only with optional `PyYAML` used if present. It does **not** execute candidate code or use networking. It parses name/description, checks canonical folder names, detects duplicates, and ranks rough category/word overlaps across Chinese and English. It also implements session scoping (`--only` / `--session`) and the read-only `context` pressure check. CLI defaults (`DEFAULT_TOP`, `DEFAULT_THRESHOLD`) are shared with the offline `eval` command so measured retrieval reflects real behavior.
- `scripts/install.py`: conservative copy + optional bootstrapping of user/project root instructions. `--force` creates a backup before replacement.
- `tests/`: offline fixtures, expected retrieval ranking and security checks. No external API calls or tokens required.
- `.github/workflows/ci.yml`: reproducible tests and lint on Python 3.10, 3.12 and 3.13.

## Native integrations

- **Claude Code:** use `.claude/skills/<name>/SKILL.md`. A project `CLAUDE.md` can provide reliable initial routing instructions. Actual activation remains controlled by Claude Code. Hosted Claude products can differ in loading method.
- **Codex:** use `.agents/skills/<name>/SKILL.md` plus project-level `AGENTS.md`; reload the session after new skill installation where needed.
- **Other Agent Skills hosts:** register the skill in their supported filesystem or managed registry; map `scan` and the full skill instruction read to the host. If an agent cannot access local files, bypass CLI and use host-exposed metadata directly.
- **OpenAI Agents API / Responses API:** follow the current hosted/sandbox skill registration mechanisms. This repository does not perform API registration or access private tool schemas.

## Resolution precedence

1. Higher-priority host/runtime instructions and safety restrictions.
2. User's current task and authorized output/action.
3. Host-required domain-specific workflows and explicitly named skills.
4. Semantic fit and prerequisites among actually accessible candidates.
5. CLI lexical scores as a shortlist convenience only.

No route score can override a required skill, user constraints or tool reality. No skill is loaded merely to satisfy a usage quota.

## Future extension points

- Host adapters may add dynamic `list_skills/read_skill/invoke_skill` bridges when the underlying host actually exposes those operations.
- For very large skill registries, replace heuristic scoring with embeddings or tool-based LLM reranking behind a privacy-preserving adapter, and evaluate with an annotated dataset.
- For auditable production use, emit host-observed `selected`, `read`, `tool-invoked`, `artifact-validated` events with trace IDs, timestamps and redacted data. Do not accept the model's unsupported self-report as proof.
- Define task-specific output quality checks and regression evaluations. See EVALUATION.md.

## Threat boundary

Third-party Skill metadata can be prompt-injection material. The local scanner does not follow symlinks, network imports or recursively inspect arbitrary folders. There is no automatic installation, subprocess execution of candidate code, outbound traffic, or credential access. See SECURITY.md.

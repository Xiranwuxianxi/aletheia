# Security policy

## Trust model

This repository's discovery helper reads only names/descriptions from locally accessible SKILL.md files. It does not execute, install, fetch, import or grant permissions to discovered skills. Selection remains subject to host and user authority. Skill content from third parties is untrusted and may include prompt injection.

## Supported version

Current 1.x release receives best-effort security fixes.

## Reporting a vulnerability

Do not publish exploitable private-user data or credentials in a public issue. Contact repository maintainers privately using the hosting platform's security-advisory channel once a public repository is configured, or report without secret reproductions. No private inbox has been preconfigured in this template.

Non-security conduct concerns (harassment, discrimination, off-topic behavior) should be handled through the [Code of Conduct](CODE_OF_CONDUCT.md) reporting path instead.

## Operator guidance

Install only trusted Skills, keep external tools least-privileged, avoid storing secrets on command lines, and test update/install changes using `--dry-run`. Treat any production file modifications or outbound operations as separately authorized actions.

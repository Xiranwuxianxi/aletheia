# Contributing

Thanks for improving skill routing. Issues, bug reports and PRs are welcome.
By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

The project is stdlib-only, so there is nothing to install to run the tests.
Optionally install the extras for stricter linting and full YAML support:

```bash
python -m pip install -e ".[dev]"
```

## Workflow

1. Open an issue describing the concrete routing or execution failure and your agent host, available skill metadata, expected choice and observed behavior. Redact private paths and credentials.
2. Add a minimal test case reproducing retrieval bugs under `tests/` when possible.
3. Keep frontmatter standard-compliant; do not add a required network service or auto-run third-party skill code to the scanner.
4. Ensure the full verification suite passes:

   ```bash
   python -m unittest discover -s tests -v
   python skills/aletheia/scripts/router.py lint --root skills
   python skills/aletheia/scripts/router.py eval --root tests/fixtures --cases tests/eval_cases.json
   ```

5. If you change the version, update `pyproject.toml`, the `SKILL.md`
   frontmatter and `CHANGELOG.md` together — a unit test enforces this.
6. Describe how the change affects false matches, safety, runtime costs and backwards compatibility.

Prefer narrowly scoped pull requests. Do not submit confidential user content in test fixtures. Code is MIT licensed by contributors upon submission.


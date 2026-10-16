# Change: Improve developer tooling and code quality

## Why
The test suite, CI, PEP 621 packaging, license fix and orphaned-module cleanup already
landed. The remaining code-quality gaps from the audit are pre-commit hooks, incremental
type hints with `mypy`, dependency pinning for reproducible installs, and a clear
documentation strategy. Closing these hardens long-term project health. (Audit D5, D6,
D11, D12.)

## What Changes
- Add a `.pre-commit-config.yaml` running `ruff`, `ruff format` (or `black`), and
  `end-of-file-fixer`.
- Add type hints incrementally to public module APIs and run `mypy` in CI (non-blocking
  first, then `--strict` on covered modules).
- Add dependency pinning for reproducible installs (a pinned `requirements.txt` or a
  lockfile) while keeping `pyproject.toml` as the source of loose constraints.
- Remove stale Sphinx/autodoc stubs; document a Markdown-first strategy (MkDocs Material
  + mkdocstrings) in `docs/README.md`.

## Impact
- Affected specs: `dev-quality`
- Affected code: `.pre-commit-config.yaml`, `pyproject.toml` (mypy config), type hints
  across modules, `requirements.txt`/lockfile, `docs/README.md`, `Makefile`, README

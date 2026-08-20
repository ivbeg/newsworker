---
title: "Contributing"
description: "Development setup, local checks, and release verification"
---

# Contributing

Issues and pull requests are welcome. Please open an issue to discuss
substantial changes before submitting a PR, and keep additions covered by the
changelog.

## Development setup

```bash
pip install -e ".[dev]"
# or, for a reproducible pinned environment:
pip install -r requirements.txt

pre-commit install
make test
make lint
mypy
```

## Local checks (CI parity)

```bash
python -m ruff format --check newsworker tests
python -m ruff check newsworker tests
python -m mypy
python -m pytest --cov=newsworker --cov-branch --cov-report=term-missing --cov-fail-under=85
python -m build
python -m twine check dist/*
python -m pip install --force-reinstall dist/*.whl
newsworker --version
openspec validate --all --strict --no-interactive
```

Optional jobs install and test the `async`, `fulltext`, `metrics`, and
`browser` extras; browser tests additionally install Chromium. The Docker smoke
builds the image, starts it bound to loopback, and probes `/health/live`.

For reproducible transitive dependencies, generate `constraints/py<minor>.txt`
from a clean environment with
`pip-compile --generate-hashes pyproject.toml --extra dev`, then install with
`pip install -c constraints/py<minor>.txt -e '.[dev]'`.

Before a release, inspect wheel contents for `newsworker/bridges` and
`py.typed`, run Twine metadata validation, install the artifact in a clean
virtual environment, and run the CLI and Docker health smoke tests.

Spec-driven changes live under `openspec/`; see [OpenSpec](/development/openspec).

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
python -m ruff format --check newsworker tests benchmarks
python -m ruff check newsworker tests benchmarks
python -m mypy
python -m pytest --cov=newsworker --cov-branch --cov-report=term-missing --cov-fail-under=85
python -m build
python -m twine check dist/*
python -m pip install --force-reinstall dist/*.whl
newsworker --version
openspec validate --all --strict --no-interactive
```

Ruff (pinned to the same version in `.[dev]`, pre-commit and CI) checks
pyflakes, imports, bugbear, Python 3.10 syntax (`UP`), simplifications (`SIM`),
bandit security rules (`S`) and complexity (`C901`, at most 15). The functions
that were already more complex carry `# noqa: C901`; remove the marker when you
simplify one, and do not add new ones. A security finding that does not apply
gets a `noqa` with the reason next to it, as in `formats.read_opml`.

Optional jobs install and test the `async`, `fulltext`, `metrics`, and
`browser` extras; browser tests additionally install Chromium. The Docker smoke
builds the image, starts it bound to loopback, and probes `/health/live`.

`requirements-lock.txt` pins every runtime and test dependency for all
supported Python versions. The `locked` CI job installs exactly that set on
Python 3.10 and 3.14 and fails if the lock no longer satisfies
`pyproject.toml`; the main test matrix keeps using the newest allowed
releases, so an upstream break shows up there without blocking a reproducible
build. Reproduce CI locally with:

```bash
pip install -r requirements-lock.txt && pip install --no-deps -e .
```

After changing dependencies, regenerate the lock (add `--upgrade` to move all
pins forward):

```bash
uv pip compile pyproject.toml --extra test --python-version 3.10 --universal --no-header -o requirements-lock.txt
```

## Releasing

1. Bump `__version__` in `newsworker/__init__.py` and turn `## [Unreleased]` in
   `CHANGELOG.md` into `## [X.Y.Z] - YYYY-MM-DD`.
2. Merge to `master`, then push the tag: `git tag -a vX.Y.Z -m "newsworker X.Y.Z" && git push origin vX.Y.Z`.
3. The `Release` workflow checks that the tag matches the package version,
   builds and validates the distributions (Twine `--strict`, wheel contains only
   `newsworker/`), creates the GitHub release with the CHANGELOG section and the
   artifacts, and pushes the image to `ghcr.io/ivbeg/newsworker`.
4. PyPI: the workflow uploads only when the repository variable
   `PYPI_TRUSTED_PUBLISHING` is `true` and a
   [trusted publisher](https://docs.pypi.org/trusted-publishers/) is configured
   on PyPI for this repository, workflow `release.yml` and environment `pypi`
   (add required reviewers to that environment to approve each upload).
   Otherwise upload the release artifacts manually with `twine upload`.

Spec-driven changes live under `openspec/`; see [OpenSpec](/development/openspec).

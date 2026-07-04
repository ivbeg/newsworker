## 1. Pre-commit
- [x] 1.1 Add `.pre-commit-config.yaml` with ruff, ruff-format (or black), end-of-file-fixer, trailing-whitespace
- [x] 1.2 Document `pre-commit install` in README/CONTRIBUTING

## 2. Type checking
- [x] 2.1 Add type hints to `settings.py`, `cache.py`, `formats.py`, `service.py` public APIs
- [x] 2.2 Add `[tool.mypy]` config to `pyproject.toml`
- [x] 2.3 Add a `mypy` CI job (start non-blocking, tighten to `--strict` per covered module)

## 3. Dependency pinning
- [x] 3.1 Generate a pinned `requirements.txt` (or lockfile) for reproducible installs
- [x] 3.2 Document install-from-pinned vs. editable/dev install

## 4. Documentation strategy
- [x] 4.1 Remove Sphinx/autodoc stubs (`docs/*.rst`, stale `docs/*.md`, `make docs`)
- [x] 4.2 Add `docs/README.md` with MkDocs Material + mkdocstrings bootstrap guide
- [ ] 4.3 (Optional follow-up) Adopt MkDocs site and CI `mkdocs build --strict`

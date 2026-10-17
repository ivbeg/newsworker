## 1. Specification
- [x] 1.1 Describe the shipped behaviour as spec deltas
- [x] 1.2 Validate with `openspec validate complete-1-4-release --strict`

## 2. Implementation (delivered in PRs #53–#66)
- [x] 2.1 Dateline, weekday and day-span dates (`dates.py`, `extractor.py`)
- [x] 2.2 Async transport parity (`async_fetch.py`, `service.py`)
- [x] 2.3 `languages`, `watch --once` (`core.py`, `language.py`)
- [x] 2.4 Mastodon channel (`delivery.py`)
- [x] 2.5 Home page form (`server.py`)
- [x] 2.6 Lint rules, typed contract, whole-package mypy (`pyproject.toml`, `model.py`)
- [x] 2.7 Locked dependencies (`requirements-lock.txt`, CI `locked` job)
- [x] 2.8 Upgrade-safe identities and generated settings reference (`dedup.py`, `settings_doc.py`)

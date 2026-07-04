# Project Context

## Purpose
`newsworker` is a Python 3 library and CLI (v1.1.0) that extracts RSS/Atom/JSON/CSV
feeds from arbitrary HTML pages by clustering date-bearing text nodes. It also
discovers existing feeds on a page, builds reusable YAML parsing specs, and can
serve generated feeds over a local HTTP server. It is built around the `qddate`
date pattern-matching engine (340+ formats across 8 languages).

## Tech Stack
- Python 3 (targets 3.9–3.12)
- CLI: Typer
- HTML parsing: lxml, BeautifulSoup4 (`bs4`)
- Date parsing: qddate
- Feed rendering: feedgen (RSS/Atom); stdlib for JSON/CSV/OPML
- HTTP client: requests (connection-pooled session with retry)
- HTTP server: stdlib `http.server.ThreadingHTTPServer` (dependency-free)
- Config/specs: YAML (`pyyaml`)

## Project Conventions

### Code Style
- Standard PEP 8; 4-space indentation; module docstrings describe responsibility.
- Prefer stdlib-only for the HTTP server; new heavy dependencies must be justified.
- Keep changes small and focused (see OpenSpec "Simplicity First").

### Architecture Patterns
Thin CLI layer (`core.py`) over a service layer (`service.py`) that orchestrates:
- `cache.py` — SHA-1-keyed file caches for specs and page content.
- `extractor.py` — dynamic date-driven feed extraction (the original algorithm).
- `spec.py` — YAML spec serialization, `SpecAnalyzer`, `SpecExtractor`.
- `finder.py` — discovers existing feeds via autodiscovery/icons/heuristics.
- `formats.py` — renders the internal feed dict to json/rss/atom/csv/opml.
- `server.py` — stdlib HTTP server exposing `/feed`, `/health`, `/`.
- `settings.py` — YAML-backed `Settings` dataclass (`~/.newsworker/config.yaml`).
- `tools.py`, `tagmapper.py`, `consts.py` — helpers and HTML-walking primitives.

Data flow: `get_feed(url)` → ContentCache → fetch → SpecCache → SpecAnalyzer →
SpecExtractor (fallback to dynamic FeedExtractor) → `format_feed()`.

### Testing Strategy
- pytest with HTML fixtures under `tests/fixtures/` and expected feed dicts.
- Prioritize deterministic unit tests for `formats.py`, `spec.py`, `settings.py`,
  `cache.py`, and the server request handling; avoid live network in unit tests.

### Git Workflow
- Feature branches with verb-scoped names (e.g. `feat/jsonfeed-output`).
- Conventional-commit-style messages (`feat(...)`, `fix(...)`, `build(...)`, `ci(...)`).

## Domain Context
The internal feed dict shape is the API contract between extraction and output:
`{title, language, link, description, items: [{title, description, pubdate,
unique_id, link, extra: {links, images}}]}`. Changes to item fields (author,
categories, full text) bump the internal API and should be batched into a minor
release to avoid churning downstream consumers.

## Important Constraints
- The HTTP server should remain dependency-free by default; optional features
  (e.g. Prometheus metrics) must degrade gracefully when their dep is absent.
- Server-side fetching must keep the baseline SSRF guard (`validate_url`) and the
  allowed-hosts allow-list intact.
- Do not regress the caching contract (SHA-1 URL keys, mtime-based freshness).

## External Dependencies
lxml, beautifulsoup4, qddate, feedgen, requests, pyyaml, typer.

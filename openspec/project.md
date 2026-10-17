# Project Context

## Purpose
`newsworker` is a Python library and CLI that turns news pages without feeds into
RSS/Atom/JSON Feed and other formats. It finds publication dates with the `qddate`
pattern engine, groups date-bearing nodes into item blocks, and stores the result as
a reusable YAML parsing spec. Around that core it discovers existing feeds, passes
native feeds through, watches sources and delivers new items (webhook, e-mail,
Telegram, Slack, Discord, Matrix), serves feeds over a local HTTP server and exposes
its tools to AI assistants over MCP.

## Tech Stack
- Python 3.10–3.14
- CLI: Typer
- HTML parsing: lxml, cssselect, BeautifulSoup4
- Date parsing: qddate (pyparsing)
- Feeds: feedgen for RSS/Atom rendering, feedparser for native feeds and verification
- HTTP client: requests/urllib3 behind one fetch policy (`fetch.py`); aiohttp optional
- HTTP server: stdlib `http.server.ThreadingHTTPServer` (dependency-free)
- Storage: file caches for specs and pages, SQLite for the delivery outbox and item history
- Config and specs: YAML (`pyyaml`)
- Optional extras: `async` (aiohttp), `fulltext` (trafilatura), `browser` (Playwright),
  `metrics` (prometheus-client), `mcp` (Model Context Protocol SDK)

## Project Conventions

### Code Style
- Ruff format and lint (pinned in pre-commit and CI); mypy on a growing module list.
- Module docstrings describe responsibility; comments explain why, not what.
- Prefer stdlib; new required dependencies must be justified. Optional features
  live behind extras and degrade with a clear message when the extra is missing.
- Keep changes small and focused (see OpenSpec "Simplicity First").

### Architecture Patterns
Thin CLI layer (`core.py`) over a service layer (`service.py`); one concern per module:
- `fetch.py` — the outbound policy: connect-time address checks, redirects, header
  stripping, size limits, robots.txt, per-host pacing (`HostScheduler`).
- `runtime.py` — request-scoped `ExtractionContext` and single-flight caching.
- `extractor.py`, `dates.py`, `relative.py` — date-driven extraction and date handling.
- `spec/` — `model.py` (YAML spec), `selectors.py`, `analyze.py` (`SpecAnalyzer`),
  `execute.py` (`SpecExtractor`).
- `native.py`, `structured.py`, `undated.py`, `jsrender.py` — further strategies.
- `finder.py` — feed discovery (autodiscovery, JSON Feed, sitemaps, WebSub).
- `formats.py` — json/rss/atom/csv/jsonfeed/html/markdown/yaml/opml rendering.
- `server.py` — `/feed` (API tokens or signed links), `/health`, `/metrics`.
- `watching.py`, `dedup.py`, `delivery.py` — watch polls, SQLite outbox with claim
  tokens and item history, delivery channels.
- `explain.py`, `diagnostics.py`, `evaluation.py` — explanations, strategy
  diagnostics, corpus scoring.
- `mcp_server.py` — MCP tools; `settings.py` — layered settings.

Strategy order in `FeedService.get_feed()`: plugin → bridge → cached or fresh spec
(re-analysed once if empty) → dynamic extraction → native feed → JSON-LD/microdata →
undated (opt-in) → browser rendering (opt-in). Links are then sanitised and item
identities assigned.

### Testing Strategy
- pytest, no live network in unit tests; coverage gate at 85%.
- Labelled extraction corpus (`tests/corpus`, 200+ cases) scored at a fixed time;
  any regression fails CI. A scheduled job checks live pages.
- `filterwarnings = error::DeprecationWarning:newsworker` keeps deprecations visible.

### Git Workflow
- Feature branches (`feat/...`, `fix/...`, `docs/...`) merged through pull requests.
- Conventional-commit messages (`feat(...)`, `fix(...)`, `build(...)`, `ci(...)`).
- Releases: bump `__version__`, date the CHANGELOG section, push tag `vX.Y.Z`;
  `release.yml` builds, creates the GitHub release and publishes the GHCR image.
  PyPI publishing runs only when trusted publishing is enabled.

## Domain Context
The internal feed dict is the API contract between extraction and output:
`{title, language, link, description, items: [{title, description, pubdate, link,
unique_id, content_hash, author?, categories?, content?, extra: {links, images}}],
provenance}`. `pubdate` is a timezone-aware datetime or `None` for undated items.
Changes to item fields are batched into minor releases.

## Important Constraints
- The HTTP server stays dependency-free by default.
- Every outbound request goes through `fetch.py`: no direct `requests.get`, no
  parser-library fetching. Private addresses stay blocked unless explicitly allowed.
- robots.txt is honoured by default; per-host pacing applies to source fetches.
- Secrets (tokens, SMTP/Matrix credentials, signing key) never appear in logs,
  diagnostics or rendered output.
- Do not regress the caching contract (SHA-1 URL keys, mtime-based freshness).

## External Dependencies
Required: pyparsing, lxml, cssselect, beautifulsoup4, qddate, typer, feedgen, pyyaml,
requests, urllib3, feedparser. Optional: aiohttp, trafilatura, playwright,
prometheus-client, mcp.

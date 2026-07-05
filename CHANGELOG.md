# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.0] - 2026-07-05

Extraction quality, spec analysis, and language detection improvements. See
[`docs/SPEC.md`](docs/SPEC.md) for the YAML spec format and `analyze` pipeline.

### Added
- **`docs/SPEC.md`** — parsing spec format, field reference, selector conventions, and
  the full `analyze` pipeline (also linked from the README and `docs/README.md`).
- **HTML `<time datetime="...">` support** — dynamic extraction and specs recognize
  ISO-8601 `datetime` attributes via the `html:time` pattern; `SpecAnalyzer` emits
  `source: attr:datetime` for these fields.
- **Text-based feed language detection** — `resolve_feed_language()` infers language from
  item title samples (Cyrillic, French, Ukrainian, and other heuristics) when page
  metadata defaults to English but content is localized.
- **`parse_datetime_attr()`** — shared ISO-8601 parser for `<time>` nodes and spec fields.
- **`analyze` fetch flags** — the same network/settings options as `extract`:
  `--user-agent`, `--language`, `--proxy`, `--timeout`, `--header`, `--cookies`,
  `--insecure`, `--ignore-robots`, `--config`, and `--json-logs`.
- **`SpecAnalysisError`** — `analyze` fails clearly when no dated news listings are found
  (`require_items=True` on the CLI path).

### Changed
- **Spec analyzer** — rejects `<select>`/`<form>` UI clusters (callback time slots),
  ignores WordPress taxonomy classes (`category-*`, `tag-*`, `post-<id>`), rejects
  overly broad bare-tag selectors, and falls back to positional `./*` XPath when CSS
  would match too many nodes.
- **Title heuristics** — prefer heading tags (`h1`–`h4`) and bold text before generic
  long-text nodes; category/archive metadata is no longer picked as the item title.
- **`decode_html`** — passes `is_html=True` to BeautifulSoup's `UnicodeDammit` so UTF-8
  pages with a `<meta charset>` are not misread (notably Cyrillic news sites).
- Bumped **qddate** to 1.0.10 in pinned `requirements.txt`.
- Test suite expanded to **175+** offline tests.

### Fixed
- WordPress and similar themes with `<time datetime>` and mixed category classes produce
  correct item counts, dates, and titles.
- Spec analysis no longer selects callback-form time-slot dropdowns over real news lists.
- Feed language on Russian/Cyrillic pages no longer stays `en` when `<html lang="en">` is
  a CMS default.

## [1.2.0] - 2026-07-04

Platform release closing the audit roadmap (formats, CLI, security, batch/watch,
plugins/bridges, Docker, CI/tests). See `openspec/changes/` for the spec breakdown.

### Security
- **TLS verification is now on by default.** `FeedExtractor.fetch` previously passed
  `verify=False` unconditionally; it now honours a new `verify_tls` setting (default
  `True`). Pass `extract --insecure` (or set `verify_tls: false`) to opt out for sites
  with broken certificate chains.
- The fetcher now respects `robots.txt`: a URL disallowed for the User-Agent raises
  `PermissionError` before any content is fetched. Controlled by the new `respect_robots`
  setting (default `True`); use `extract --ignore-robots` to override. Robots retrieval
  failures are treated leniently (fetch allowed) and parsed rules are cached per host.
- The local feed server applies a baseline SSRF guard: `/feed?url=` only accepts
  `http(s)` URLs and, when `allowed_hosts` is non-empty, restricts which hosts it will
  fetch. Only expose the server beyond localhost with an allow-list and a reverse proxy.
- Fetches are capped at `max_content_bytes` (default 10 MiB) and streamed so an
  oversized or hostile page cannot exhaust memory.

### Added
- **Output formats:** `jsonfeed` (JSON Feed 1.1), `html`, `markdown`, and `yaml` for
  `extract` and `/feed`.
- **CLI ergonomics:** `--limit`/`-n`, `--since`/`--until`, `--max-pages`, `--user-agent`,
  `--proxy`, `--timeout`, repeatable `--header`, `--cookies`, `--language`, `--json-logs`,
  top-level `--version`, and `--full-text` (with the `fulltext` extra).
- **`cache` subcommand** (`stats`, `list`, `clear`) with `--specs`/`--content` scoping.
- **`batch` command** — concurrent extraction from `--urls-file` or `--from-opml`, with
  optional `--async` transport (`newsworker[async]`).
- **`watch` command** — interval polling with SQLite deduplication, webhook delivery, and
  pagination; clean shutdown on SIGINT/SIGTERM.
- **`scan --sitemap`** — discover feed URLs from `/sitemap.xml`.
- **Feed enrichment:** per-item `author` and `categories`; optional `content` via
  `--full-text` (`newsworker.enrich`).
- **Plugins and bridges:** third-party extractors via the `newsworker.extractors` entry-point
  group; per-site YAML bridges in `newsworker/bridges/` and `~/.newsworker/bridges/`.
- **Fuzzy dates and language detection** — relative strings ("2 hours ago", "yesterday") and
  `<html lang>` / `Content-Language` replace the hardcoded English default.
- **HTTP caching:** feed-server `ETag`/`Last-Modified` with `304 Not Modified`; upstream
  conditional revalidation (`If-None-Match` / `If-Modified-Since`); atomic per-key cache
  writes under concurrent access.
- **Optional `/metrics`** endpoint when `prometheus_client` is installed (`metrics` extra).
- **Docker** — `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and a CI image build.
- **Developer tooling** — pytest suite (145+ offline tests), GitHub Actions (Python
  3.8–3.12 + ruff + mypy), `.pre-commit-config.yaml`, pinned `requirements.txt`, PEP 621
  `pyproject.toml`.
- **Cache eviction** settings: `content_cache_max_entries`, `content_cache_max_bytes`,
  `spec_cache_max_entries` (`0` = unbounded).
- **`FeedService.get_feeds`** for concurrent multi-URL extraction with isolated per-URL errors.

### Changed
- Feed item dict shape gained optional `author`, `categories`, and `content` keys. RSS/Atom
  enclosure length uses a known value when available instead of always emitting `0`.
- Migrated packaging to PEP 621 `pyproject.toml`; removed `setup.py`/`setup.cfg`. License
  metadata is MIT everywhere. Ruff, pytest, and mypy config live in `pyproject.toml`.
- Modernised the `Makefile` (`ruff`/`pytest`/`build`/`twine`; removed the broken Sphinx
  `make docs` target).
- Unified `filtered_text_length` to 150 across extractor, settings, and CLI.
- **Documentation:** README expanded for the full CLI surface; stale Sphinx/autodoc stubs
  removed; `docs/README.md` documents a MkDocs Material + mkdocstrings bootstrap path.
- `FeedExtractor.learn_feed` delegates to `get_feed` instead of duplicating the pipeline.

### Fixed
- `get_abs_url` preserves the base scheme (notably `https`) via `urllib.parse.urljoin`.
- `FeedExtractor.process_clusters` no longer mis-scopes link/image/date detection; items
  keep their own `link`/`image` and are not dropped when description assembly fails.
- `FeedExtractor.match_text` always returns a 5-tuple so `SpecExtractor` no longer crashes
  on unparseable dates.
- `FeedsFinder.find_feeds(..., include_entries=True)` no longer raises `KeyError`.
- Logging defaults to `WARNING`; `--verbose` raises it to `DEBUG` (no import-time `basicConfig`).

### Removed
- Stale Sphinx/autodoc stubs under `docs/` and the `make docs` target.
- Unused, import-broken `newsworker/feed.py` module.
- Undeclared `chardet` import in `finder.py`.
- Stale `README.rst` / `HISTORY.rst` duplicates (Markdown docs are canonical).

### Internal
- Refactored `FeedExtractor.process_clusters` into `_build_item_blocks` / `_item_from_block`.
- New modules: `enrich`, `dedup`, `delivery`, `plugins`, `bridges`, `async_fetch`.

## [1.1.0] - 2026-07-03

### Added
- New `serve` command running a local HTTP feed server (standard-library only,
  no extra dependencies) that turns any page URL into a feed on demand over GET
  (`GET /feed?url=<page>&format=atom`), plus `/health` and `/` endpoints. Feed
  URLs can be pasted straight into any RSS reader.
- New `analyze` command that runs the dynamic heuristics once and distils them
  into a reusable YAML parsing **spec**, and a `--spec` / `-s` option for
  `extract` to run fast, deterministic extraction from a pre-built spec.
- Reusable parsing specs via the new `newsworker.spec` module
  (`FeedSpec`, `SpecAnalyzer`, `SpecExtractor`) — deterministic CSS/XPath
  selectors that avoid re-running the discovery heuristics on known layouts.
- Caching layer (`newsworker.cache`) with a **spec cache** and a **content
  cache** (configurable TTL), so `extract` and `serve` avoid rebuilding specs
  and re-fetching pages. New `--no-cache`, `--refresh` and `--config` / `-c`
  options for `extract`, and `--cache-dir` / `--content-ttl` for `serve`.
- Settings support (`newsworker.settings`) backed by a YAML config file at
  `~/.newsworker/config.yaml` (created with defaults on first run), controlling
  cache directory, TTLs, server host/port and detection parameters.
- High-level `newsworker.service.FeedService` tying together caching, spec
  building and extraction; shared by both the `extract` command and the server.
- Multiple output formats for the `extract` command via `--format` / `-f`:
  `json` (default), `rss`, `atom` and `csv`.
- Multiple output formats for the `scan` command via `--format` / `-f`:
  `json` (default), `rss`, `atom`, `csv` and `opml` (subscription list).
- `--output` / `-o` option for `extract` and `scan` to write results to a file
  instead of stdout.
- New `newsworker.formats` module with `format_feed()` and `format_scan()`
  helpers (RSS/Atom generated via `feedgen`, plus CSV and OPML serializers).

### Changed
- Rewrote `README.md` with a modern structure: table of contents, CLI reference
  tables, output-format and caching documentation, and up-to-date library usage
  examples.
- `extract` now builds and caches a parsing spec on first use (plus the fetched
  page content) so subsequent runs are faster; pass `--spec` to use an explicit
  spec.
- `scan` now emits structured, format-aware output instead of a raw pretty-print.
- Added `cssselect`, `pyyaml`, `requests` and `urllib3` as dependencies (and
  declared `feedparser` explicitly in `setup.py`).
- Moved `PERFORMANCE_ANALYSIS.md` under `docs/` and removed the standalone
  `AUTHORS.md` (authorship is tracked in `setup.py` and the README).

### Fixed
- Naive datetimes are normalized to UTC when rendering RSS/Atom feeds, as
  required by the feed formats.

## [1.0.1] - 2018-07-21

### Added
- First public release on PyPI and github

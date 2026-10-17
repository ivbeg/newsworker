# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Two-digit years** — `25/7/22` and `16.10.26` resolve to 2022 and 2026 instead
  of years 22 and 26 AD (#14).
- **Offsets written in text** — `10:00:00 +0300`, `10:00 -0500` and
  `10:00 GMT+3` are converted to UTC instead of being read as UTC wall time.
  The signed `timezone` token reported by newer qddate releases is understood.
- **Implausible dates** (before 1970 or more than a year ahead) are ignored
  rather than clustered as news dates; dates printed without a year roll back to
  the previous year around New Year.
- A failure while extracting with cached date patterns no longer leaves the
  narrowed qddate session active for later requests.

### Added
- **Extraction corpus and quality gate** — 182 labelled listing pages across 8
  languages and 13 CMS layouts (`tests/corpus`), scored by the new
  `newsworker.evaluation` module. CI fails when precision, recall, title or date
  accuracy drops, and publishes the per-case report in the job summary.
- **Live smoke check** — `benchmarks/live_check.py` extracts a few public news
  pages weekly and fails on missing items, dates or links (replaces the
  example.com smoke run, which had no news to find).
- **Flat listings** — pages whose items are sibling elements with no wrapper
  (heading, date line, teaser, "read more") are now analysed as heading-led
  groups (`items.group: siblings` in specs). Seen on postgresql.org.

- **Structured data** — JSON-LD (`ItemList`, `@graph`, `NewsArticle`,
  `BlogPosting`, ...) and microdata article lists are read. They supply the
  items when a page shows no dates, and sharpen same-day dates with the exact
  time and add authors otherwise. Disable with `structured_data: false`.
- **Relative dates in 8 languages** — "3 hours ago", "вчера в 14:30",
  "2 дні тому", "vor 3 Tagen", "il y a 2 jours", "hace un día",
  "2 giorni fa", "há 3 dias" and today/yesterday words in en, ru, uk, de, fr,
  es, it and pt (previously English only).
- `FeedService(clock=...)` resolves relative dates against an injected time.

### Fixed (accuracy)
- **Article links** — the headline link is chosen instead of the first link in
  an item, which was often a category or tag link (#19).

### Changed (requests)
- **User-Agent** — requests now identify as
  `newsworker/<version> (+https://github.com/ivbeg/newsworker)` instead of
  posing as Chrome 23. Sites such as w3.org and gnu.org reject the old string;
  `robots.txt` rules for `newsworker` now match. Use `--user-agent` or the
  `user_agent` setting to override.

### Fixed (reliability)
- **Stale inferred specs** — when a cached, automatically inferred spec matches
  no items (the site changed its layout), the page is re-analysed once and the
  new spec replaces the old one; otherwise dynamic extraction runs. Explicit
  specs and bridges are never replaced silently.
- **Stable item identity** — `unique_id` is derived from the item's own link,
  so editing a teaser no longer makes `watch` or feed readers see a "new" item.
  The previous text hash is kept as `content_hash`.
- **Stable output and HTTP validators** — per-request timing and cache state are
  no longer embedded in `provenance`; RSS/Atom build dates come from the newest
  item. The server sends a weak `ETag` over the feed content and
  `Last-Modified` from the newest item, so unchanged feeds return `304`.
- **Self links** — RSS/Atom `rel="self"` and JSON Feed `feed_url` point at the
  server's `/feed` URL (configure `public_base_url` behind a proxy) instead of
  the source page.
- **Specs** — `source: href|src|datetime` aliases work at extraction time, a
  class-only CSS selector such as `.news-card` is no longer mistaken for XPath,
  and `items.container` and `patterns` are validated. An explicit
  `--language` / `default_language` now wins over a spec's language; the undated
  fallback detects the language instead of assuming English.
- **URLs** — tracking-parameter cleanup keeps encoded delimiters, repeated keys,
  blank values and fragments (`?id=a%26b&tag=1&tag=2#x` round-trips), and also
  removes `fbclid`, `gclid`, `yclid`, `utm_term`, `utm_id` and Mailchimp ids.
- **Caches** — corrupt content metadata or a malformed cached spec is treated as
  a miss and refetched instead of failing the request; a `304` response stores
  the new validators. Local files and stdin no longer read or overwrite the
  spec cached for the live site; local input is capped at `max_content_bytes`.
- **Pagination** — follow-up pages reuse the first page's spec instead of
  caching one spec per `?page=N`, overlapping pages are de-duplicated, and an
  aborted pagination is reported in diagnostics.
- **Full text** — failures are reported in warnings, and readability output is
  labelled `content_kind: html` instead of `text`.
- **Watch** — due deliveries are drained before the page is fetched, so a source
  outage no longer blocks earlier items; `--format rss|atom|…` is honoured on
  stdout; finite runs exit non-zero on fetch failures or pending/terminal
  deliveries; outbox claims carry an owner token so a worker whose lease expired
  cannot overwrite a newer delivery; delivered history is pruned every poll.
- **Webhook helper** — `deliver_webhook()` gives every item its own idempotency
  key and retries only the items that failed.
- **Scan / extract exit codes** — `scan` of an unreachable page exits `1`
  instead of printing an empty result; both commands accept `--fail-on-empty`
  (exit `3`).
- **Bridges** — user bridges override bundled ones, and `match.hosts` lists
  apply to every listed host.
- **Batch** — manifests report the transport actually used, per-source timings
  and cache state; a source that cannot be written is recorded as a failure
  instead of aborting the batch; duplicate URLs are processed once.

### Security
- **Connection-time address check** — the address a socket actually connects
  to is validated against the private-network policy, closing the DNS
  rebinding window between resolution and connection.
- **Credentials on redirects** — `Authorization`, `Cookie`, `X-API-Key` and all
  configured `extra_headers` are dropped when a redirect leaves the origin.
- **Delivery isolation** — webhook and Telegram requests no longer inherit the
  source `extra_headers`.
- **Environment proxies** — `HTTP(S)_PROXY`, `NO_PROXY` and `.netrc` are ignored
  unless the new `trust_env_proxy` setting is enabled.
- **Unsafe links** — `javascript:`, `data:` and other non-http(s) item links and
  images are removed from every output; the HTML preview also carries a CSP.
- **Server refresh** — `?refresh=1` is honoured only for loopback clients or
  token-authenticated requests.

### Changed
- Each thread uses its own pooled HTTP session, so concurrent server requests
  and full-text fetches no longer serialise behind one locked session.
- **Python 3.10+** is required; Python 3.14 is tested. Python 3.9 reached
  end of life in October 2025.
- Importing `newsworker` no longer configures the root logger or silences
  urllib3's `InsecureRequestWarning` process-wide. The CLI configures logging in
  `cli()`, and `--insecure` silences the warning for that run only.
- The qddate parser is built once per thread and reused, instead of once per
  request (about 33 ms per feed build on a laptop).
- Replaced lxml's deprecated `getchildren()` and removed dead debug comments.
- README and docs: publish the Docker port on `127.0.0.1` in examples; describe
  timezone handling and the `--undated` fallback accurately.
- Reorganized documentation into a Docusaurus site under `docs/` (Getting
  Started, Use Cases, CLI Reference, Guides, Integrations, Development), with a
  GitHub Pages workflow at `.github/workflows/deploy-docs.yml`.

## [1.3.0] - 2026-07-05

Extraction quality, spec analysis, and language detection improvements. See
[parsing specs](docs/docs/guides/parsing-specs.md) for the YAML spec format and `analyze` pipeline.

### Added
- **Parsing spec docs** — YAML format, field reference, selector conventions, and
  the full `analyze` pipeline (now at `docs/docs/guides/parsing-specs.md`).
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

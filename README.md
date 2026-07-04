# newsworker

[![PyPI version](https://img.shields.io/pypi/v/newsworker.svg?style=flat-square)](https://pypi.python.org/pypi/newsworker)
[![Python versions](https://img.shields.io/pypi/pyversions/newsworker.svg?style=flat-square)](https://pypi.python.org/pypi/newsworker)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

> Turn any news page into an RSS/Atom feed — even when the site publishes no feed at all.

`newsworker` is a Python 3 library and command-line tool that **extracts news feeds from plain HTML pages**. It is built for the common case where a site publishes fresh news but offers no RSS/ATOM feed, and where generic "page change" monitors are too noisy to be useful.

The extracted feed can be emitted as **JSON, JSON Feed 1.1, RSS, Atom, CSV, HTML, Markdown, YAML or OPML**, so you can plug it straight into a feed reader, a pipeline, or your own storage.

---

## Table of contents

- [How it works](#how-it-works)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Command-line interface](#command-line-interface)
  - [`extract` — build a feed from a page](#extract--build-a-feed-from-a-page)
  - [`serve` — local feed server](#serve--local-feed-server)
  - [`scan` — discover existing feeds](#scan--discover-existing-feeds)
  - [`analyze` — generate a reusable spec](#analyze--generate-a-reusable-spec)
  - [`batch` — extract feeds from many pages](#batch--extract-feeds-from-many-pages)
  - [Plugins, bridges and async transport](#plugins-bridges-and-async-transport)
  - [`watch` — poll a page and deliver only new items](#watch--poll-a-page-and-deliver-only-new-items)
  - [`cache` — inspect and manage caches](#cache--inspect-and-manage-caches)
  - [`parsedate` — inspect date parsing](#parsedate--inspect-date-parsing)
- [Settings and caching](#settings-and-caching)
- [Output formats](#output-formats)
- [Library usage](#library-usage)
- [Features](#features)
- [Supported languages](#supported-languages)
- [Performance](#performance)
- [Limitations](#limitations)
- [Dependencies](#dependencies)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## How it works

The core idea is simple. Most news pages carry a **publication date** next to each item — `2017-09-27`, `1 jul 2016`, `18/06/2018`, and hundreds of other variants. `newsworker`:

1. **Finds every date** on the page using [qddate](https://github.com/ivbeg/qddate), a fast pattern-based date parser that recognizes 340+ date formats across many languages.
2. **Clusters** repeated, similarly-structured date nodes to tell apart a *page* date (footer, "last updated") from the *news list* area.
3. **Reconstructs each news item** around its date node, pulling out the title, description, link and image.

The result is a structured feed you can serialize into whatever format you need.

---

## Installation

Requires **Python 3.7+**.

```bash
pip install newsworker              # runtime
pip install -e ".[dev]"             # editable + pytest, ruff, mypy, pre-commit
pip install newsworker[fulltext]    # optional: trafilatura for --full-text
pip install newsworker[async]       # optional: aiohttp for batch --async
pip install newsworker[metrics]     # optional: Prometheus /metrics endpoint
```

Installing from source:

```bash
git clone https://github.com/ivbeg/newsworker.git
cd newsworker
pip install -e ".[dev]"
```

### Docker

Run the feed server in a container (binds to `0.0.0.0:8787`):

```bash
docker build -t newsworker .
docker run --rm -p 8787:8787 -v newsworker-home:/home/newsworker/.newsworker newsworker
```

Or with Compose (persists config/cache in a named volume):

```bash
docker compose up
```

---

## Quick start

Extract a feed from a page and print it as RSS:

```bash
newsworker extract "https://www.eib.org/en/index.htm" --format rss
```

Discover feeds already published on a site and export them as an OPML subscription list:

```bash
newsworker scan "https://www.dta.gov.au/news/" --format opml --output feeds.opml
```

Or use it directly from Python:

```python
from newsworker.extractor import FeedExtractor

extractor = FeedExtractor(filtered_text_length=150)
feed, session = extractor.get_feed(url="https://www.eib.org/en/index.htm")

for item in feed["items"]:
    print(item["pubdate"], item["title"])
```

---

## Command-line interface

The package installs a single `newsworker` executable exposing eight commands:

```text
newsworker [COMMAND] [ARGS] [OPTIONS]

Commands:
  extract    Extract feed records from a web page
  serve      Run a local HTTP server exposing pages as feeds
  scan       Scan a page and find existing feeds
  analyze    Analyze a page and generate a reusable YAML parsing spec
  batch      Extract feeds from many pages concurrently
  watch      Poll a page and emit/deliver only new items
  cache      Inspect and manage the spec and content caches
  parsedate  Parse a date/time string (debugging helper)
```

Add `--verbose` / `-v` to any command for detailed execution logs. Run
`newsworker --version` to print the installed version.

### `extract` — build a feed from a page

Extracts news items from an HTML page and renders them in the chosen format.

```bash
newsworker extract URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `json` | Output format: `json`, `jsonfeed`, `rss`, `atom`, `csv`, `html`, `markdown`, `yaml`. |
| `--output` | `-o` | *(stdout)* | Write the result to a file instead of printing it. |
| `--spec` | `-s` | — | Path to a YAML spec produced by `analyze`. Uses fast deterministic extraction instead of the dynamic heuristics. |
| `--limit` | `-n` | — | Maximum number of items to emit. |
| `--max-pages` | | `1` | Follow up to N "next" links, merging items across pages. |
| `--since` | | — | Only items on or after this date (`YYYY-MM-DD`). |
| `--until` | | — | Only items on or before this date (`YYYY-MM-DD`). |
| `--full-text` | | `false` | Follow each item link and extract the full article body into `content` (needs the `fulltext` extra: `pip install newsworker[fulltext]`). |
| `--user-agent` | | *(built-in)* | Override the User-Agent used for fetching. |
| `--language` | | *(auto)* | Override the auto-detected feed language (e.g. `en`, `fr`). |
| `--proxy` | | — | Proxy URL for outgoing requests (e.g. `http://host:port`). |
| `--timeout` | | `30` | HTTP request timeout in seconds. |
| `--header` | | — | Extra HTTP header `Key: Value` (repeatable). |
| `--cookies` | | — | Path to a Netscape/Mozilla cookie jar file. |
| `--insecure` | | `false` | Disable TLS certificate verification for this run. |
| `--ignore-robots` | | `false` | Fetch even when the site's `robots.txt` disallows it. |
| `--json-logs` | | `false` | Emit logs as structured JSON. |
| `--no-cache` | | `false` | Bypass the spec and content caches for this run. |
| `--refresh` | | `false` | Force re-fetching the page, ignoring cached content. |
| `--config` | `-c` | *(default)* | Path to a settings YAML file (see [Settings and caching](#settings-and-caching)). |
| `--verbose` | `-v` | `false` | Verbose logging. |

By default `newsworker` verifies TLS certificates and honors the target site's
`robots.txt`; use `--insecure` / `--ignore-robots` to override per run. Relative
dates such as "2 hours ago" or "yesterday" are resolved automatically.

By default, `extract` builds a parsing spec **dynamically on the first run** for a
URL and caches it, along with the fetched page content, under the configured
cache directory. Subsequent runs reuse the cached spec (deterministic, fast) and
the cached page (until its TTL expires). See [Settings and caching](#settings-and-caching).

Examples:

```bash
# Default JSON output
newsworker extract "https://example.com/news"

# RSS 2.0 to stdout
newsworker extract "https://example.com/news" -f rss

# Atom saved to a file
newsworker extract "https://example.com/news" -f atom -o feed.xml

# CSV table of items
newsworker extract "https://example.com/news" -f csv -o news.csv

# Fast, repeatable extraction using a pre-built spec
newsworker extract "https://example.com/news" -s example.yaml -f rss

# Ignore caches and re-fetch the page
newsworker extract "https://example.com/news" --refresh
```

### `serve` — local feed server

Runs a lightweight local HTTP server (built on the Python standard library, no
extra dependencies) that turns any page URL into a feed **on demand over GET**.
Because the feed URLs are plain GET requests, you can paste them straight into
any RSS reader and let it poll for updates.

```bash
newsworker serve [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--host` | `-h` | `127.0.0.1` | Interface to bind. Overrides the settings value. |
| `--port` | `-p` | `8787` | Port to listen on. Overrides the settings value. |
| `--config` | `-c` | *(default)* | Path to a settings YAML file. |
| `--cache-dir` | | *(settings)* | Directory for cached specs and page content. |
| `--content-ttl` | | *(settings)* | Seconds a cached page stays fresh. |
| `--verbose` | `-v` | `false` | Verbose logging. |

Endpoints:

| Route | Description |
| --- | --- |
| `GET /feed?url=<page>&format=atom` | Build a feed from `<page>`. `format` is one of `atom` (default), `rss`, `json`, `jsonfeed`, `csv`, `html`, `markdown`, `yaml`. Add `&refresh=1` to bypass the caches for one request. Responses include `ETag` / `Last-Modified`; send `If-None-Match` to receive `304 Not Modified`. |
| `GET /health` | Health check (returns `ok`). |
| `GET /metrics` | Prometheus metrics when `prometheus_client` is installed (`newsworker[metrics]`); otherwise `404`. |
| `GET /` | Short usage help. |

Example — start the server and subscribe from a reader:

```bash
newsworker serve --port 8787
```

Then add this URL to your RSS reader (URL-encode the page URL):

```text
http://127.0.0.1:8787/feed?url=https%3A%2F%2Fexample.com%2Fnews&format=atom
```

The first request for a URL builds and caches a parsing spec dynamically; later
requests reuse the cached spec and serve the cached page content until its TTL
expires, so the reader can poll frequently without hammering the source site.

> **Security note:** the server fetches whatever URL is passed to `/feed?url=`,
> so it is a server-side request forgery (SSRF) surface. It binds to
> `127.0.0.1` by default. If you expose it on a routable interface (`--host`),
> restrict what it can fetch with the `allowed_hosts` setting, and place it
> behind authentication/a reverse proxy. Only `http(s)` URLs are accepted and
> responses are capped at `max_content_bytes`. TLS certificates are verified and
> `robots.txt` is honored by default.

### `scan` — discover existing feeds

Scans a page for already-published RSS/Atom feeds (via autodiscovery links, feed icons and link heuristics) and reports them.

```bash
newsworker scan URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `json` | Output format: `json`, `rss`, `atom`, `csv`, `opml`. |
| `--sitemap` | | `false` | Also discover feed URLs from the site's `/sitemap.xml`. |
| `--output` | `-o` | *(stdout)* | Write the result to a file instead of printing it. |
| `--verbose` | `-v` | `false` | Verbose logging. |

Examples:

```bash
# Default JSON list of discovered feeds
newsworker scan "https://www.dta.gov.au/news/"

# OPML subscription list ready to import into a feed reader
newsworker scan "https://www.dta.gov.au/news/" -f opml -o feeds.opml

# CSV table of discovered feeds
newsworker scan "https://www.dta.gov.au/news/" -f csv

# Represent each discovered feed as an entry in a single RSS/Atom feed
newsworker scan "https://www.dta.gov.au/news/" -f rss
```

> **Note:** `scan` verifies every candidate feed by parsing it, so it may take longer than a raw link scan. `feedtype`, `num_entries` and `language` metadata are included where available.

### `analyze` — generate a reusable spec

Runs the dynamic heuristics once and distills them into a portable **YAML parsing spec**. Feeding that spec back into `extract --spec` skips the expensive analysis step and runs deterministic selectors, which is far faster on repeat crawls of the same layout.

```bash
newsworker analyze URL [--output spec.yaml]
```

```bash
newsworker analyze "https://example.com/news" -o example.yaml
newsworker extract "https://example.com/news" -s example.yaml -f rss
```

### `batch` — extract feeds from many pages

Extracts feeds from a list of pages concurrently, writing one file per URL.

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--urls-file` | | — | Text file with one page URL per line. |
| `--from-opml` | | — | OPML file; each outline's `htmlUrl` (or `xmlUrl`) is used as the page URL. |
| `--output-dir` | `-d` | `.` | Directory for one output file per URL. |
| `--format` | `-f` | `json` | Output format (same set as `extract`). |
| `--max-workers` | | `4` | Concurrent workers (thread pool, or aiohttp when `--async`). |
| `--async` | | `false` | Use the optional aiohttp transport (`newsworker[async]`). |
| `--no-cache` | | `false` | Bypass caches for this run. |
| `--config` | `-c` | *(default)* | Path to settings YAML. |
| `--verbose` | `-v` | `false` | Verbose logging. |

```bash
# One URL per line
newsworker batch --urls-file urls.txt --output-dir out --format rss

# Or reuse an OPML subscription list (uses each feed's htmlUrl as the page)
newsworker batch --from-opml feeds.opml -d out -f json --max-workers 8

# Optional aiohttp transport for high-throughput fetches (install the async extra)
pip install 'newsworker[async]'
newsworker batch --urls-file urls.txt -d out --async
```

### Plugins, bridges and async transport

**Third-party plugins** register extractors via the `newsworker.extractors` setuptools
entry-point group. Each plugin implements `matches(url)` and
`extract(url, data=None, **kwargs)` returning the internal feed dict. Matching plugins
are consulted before built-in spec/dynamic extraction.

**Site bridges** are YAML files with a `match:` block (`host`, optional `path` fnmatch)
and a `spec:` body (the same shape as an `analyze` spec). Bundled examples live under
`newsworker/bridges/`; drop overrides in `~/.newsworker/bridges/` (or set `bridges_dir`
in config). When a URL matches, the bridge spec is applied without running heuristics.

```yaml
match:
  host: example.com
  path: /news*
spec:
  version: 1
  items:
    selector: li.news-item
  fields:
    date: {selector: span.date, source: text, required: true}
    title: {selector: a, source: text}
    link: {selector: a, source: attr:href, absolute: true}
```

**Async batch fetches** (`batch --async`) use `aiohttp` when the `[async]` extra is
installed; otherwise the command falls back to the default thread pool.

### `watch` — poll a page and deliver only new items

Polls a page on an interval, tracks which items it has already seen (in a SQLite
store under the cache dir), and emits or POSTs only new items.

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--interval` | `-i` | `300` | Seconds between polls. |
| `--webhook` | | — | POST new items as JSON to this URL (with retry/backoff). |
| `--format` | `-f` | `json` | Output format when not using a webhook. |
| `--max-pages` | | `1` | Pages to follow per poll (pagination). |
| `--max-iterations` | | `0` | Stop after N polls (`0` = run until interrupted). |
| `--config` | `-c` | *(default)* | Path to settings YAML. |
| `--verbose` | `-v` | `false` | Verbose logging. |

```bash
# Print new items every 5 minutes
newsworker watch "https://example.com/news" --interval 300

# Deliver new items to a webhook, following pagination
newsworker watch "https://example.com/news" -i 600 --webhook https://hooks.example/new --max-pages 3
```

The loop shuts down cleanly on Ctrl-C / SIGTERM. Use `--max-iterations N` to stop
after N polls (handy for cron-style single runs).

### `cache` — inspect and manage caches

Inspects or clears the spec and content caches (see [Settings and caching](#settings-and-caching)).

```bash
newsworker cache stats            # entry counts and total size per cache
newsworker cache list             # list cached entries
newsworker cache clear            # delete all cached specs and content
newsworker cache clear --content  # scope to a single cache (--specs / --content)
```

### `parsedate` — inspect date parsing

A debugging helper that shows how `qddate` interprets a date string.

```bash
newsworker parsedate "18/06/2018"
```

---

## Settings and caching

Both `extract` and `serve` share a small caching layer that avoids redundant
work:

- **Spec cache** — the parsing spec for a URL is built dynamically on first use
  and stored as YAML. Subsequent runs reuse it (fast, deterministic).
- **Content cache** — the fetched page bytes are stored with a configurable
  time-to-live, so a page is not re-downloaded on every request while it is
  still fresh.

Settings are read from a YAML file, by default `~/.newsworker/config.yaml`
(created with defaults on first run). Point to a different file with
`--config` / `-c`.

```yaml
cache_dir: ~/.newsworker/cache   # where cached specs and page content live
content_ttl: 3600                # seconds a cached page stays fresh
spec_ttl: 0                      # seconds a cached spec is valid (0 = never expires)
host: 127.0.0.1                  # local server bind interface
port: 8787                       # local server port
filtered_text_length: 150        # max text length considered for date detection
max_content_bytes: 10485760      # cap on fetched response size (bytes)
allowed_hosts: []                # feed-server host allow-list ([] = any host)
content_cache_max_entries: 0     # max cached pages on disk (0 = unbounded)
content_cache_max_bytes: 0       # max total cached-page size on disk (0 = unbounded)
spec_cache_max_entries: 0        # max cached specs on disk (0 = unbounded)
verify_tls: true                 # verify TLS certificates on outgoing requests
respect_robots: true             # honor robots.txt before fetching
request_timeout: 30              # HTTP request timeout (seconds)
proxy: ""                        # proxy URL for outgoing requests ("" = none)
extra_headers: {}                # extra HTTP headers sent with every request
cookies_file: ""                 # optional Netscape/Mozilla cookie jar path
default_language: ""             # feed language override ("" = auto-detect)
bridges_dir: ""                  # user site-bridge YAML dir ("" = ~/.newsworker/bridges)
use_async: false                 # use aiohttp for batch --async (needs [async] extra)
full_text: false                 # follow item links and populate content (needs [fulltext])
full_text_workers: 4             # concurrency for --full-text fetches
```

Cached specs live under `<cache_dir>/specs/` and cached page content under
`<cache_dir>/content/`, keyed by a hash of the source URL. Use `--no-cache`
(bypass caches) or `--refresh` / `?refresh=1` (force a re-fetch) to override the
caches for a single run/request.

---

## Output formats

### `extract`

| Format | Description |
| --- | --- |
| `json` | The raw internal representation (feed metadata + items). Default. |
| `jsonfeed` | [JSON Feed 1.1](https://jsonfeed.org/version/1.1) document. |
| `rss`  | RSS 2.0 document generated with [`feedgen`](https://github.com/lkiesow/python-feedgen). |
| `atom` | Atom 1.0 document generated with `feedgen`. |
| `csv`  | Flat table of items: `title, link, pubdate, description, image, unique_id`. |
| `html` | A standalone HTML preview page rendering items as cards. |
| `markdown` | A Markdown bulleted list (date, title, link per item). |
| `yaml` | The feed dictionary serialized as YAML (symmetric with the spec format). |

### `scan`

| Format | Description |
| --- | --- |
| `json` | The raw list of discovered feeds. Default. |
| `rss` / `atom` | Each discovered feed becomes an entry (its title and URL), so a feed reader can browse them. |
| `csv`  | Flat table: `title, url, feedtype, num_entries, language, confidence`. |
| `opml` | OPML 2.0 subscription list — the standard interchange format for importing feeds into readers. |

Dates coming from HTML are timezone-naive; when rendering RSS/Atom they are assumed to be **UTC** (a requirement of the feed formats).

---

## Library usage

### High-level service (recommended)

`FeedService` ties together caching, spec building, bridges, plugins, enrichment and
optional pagination — shared by `extract`, `serve`, `batch` and `watch`:

```python
from newsworker.service import FeedService
from newsworker.formats import format_feed

service = FeedService()
feed = service.get_feed("https://example.com/news", max_pages=2)
print(format_feed(feed, fmt="rss"))
```

### Extract a feed dynamically

```python
from newsworker.extractor import FeedExtractor

extractor = FeedExtractor(filtered_text_length=150)
feed, session = extractor.get_feed(url="https://www.eib.org/en/index.htm")
```

`feed` is a dictionary shaped like:

```python
{
    "title": "European Investment Bank (EIB)",
    "language": "en",
    "link": "https://www.eib.org/en/index.htm",
    "description": "European Investment Bank (EIB)",
    "items": [
        {
            "title": "Blockchain Challenge: coders at the EIB",
            "description": "...",
            "pubdate": datetime.datetime(2018, 6, 18, 0, 0),
            "unique_id": "f9d359f76118076c5331ffec3cdb82eb",
            "link": "https://www.youtube.com/watch?v=YlKa2LZgxhE",
            "author": "Jane Doe",          # optional, when detected
            "categories": ["EU", "Finance"], # optional, when detected
            "content": "...full text...",    # optional, only with --full-text
            "extra": {"links": [...], "images": [...]},
            "raw_html": b"...",
        },
        # ...
    ],
    "cache": {"pats": ["dt:date:date_1"]},
}
```

### Render a feed in any format

```python
from newsworker.formats import format_feed

print(format_feed(feed, fmt="rss", public_url="https://example.com/feed.xml"))
print(format_feed(feed, fmt="atom"))
print(format_feed(feed, fmt="csv"))
```

### Reuse cached date patterns (big speed-up)

Re-parsing the same site is dramatically faster if you reuse the date patterns discovered on the first pass — it narrows matching from ~350 patterns down to the 2–3 that actually occur:

```python
pats = feed["cache"]["pats"]
feed, session = extractor.get_feed(
    url="https://www.eib.org/en/index.htm", cached_p=pats
)
```

### Set a custom User-Agent

```python
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 Chrome/23 Safari/537.11"
feed, session = extractor.get_feed(
    url="https://www.eib.org/en/index.htm", user_agent=USER_AGENT
)
```

### Analyze once, extract fast (spec workflow)

```python
from newsworker.spec import SpecAnalyzer, SpecExtractor, FeedSpec

# 1. Build and persist a spec.
spec = SpecAnalyzer(filtered_text_length=150).analyze("https://example.com/news")
spec.save("example.yaml")

# 2. Reuse it later with deterministic, low-overhead extraction.
spec = FeedSpec.load("example.yaml")
feed = SpecExtractor().extract("https://example.com/news", spec)
```

### Find existing feeds on a page

```python
from newsworker.finder import FeedsFinder

finder = FeedsFinder()

# Fast: collect candidate feed links without verifying them.
finder.find_feeds("https://www.dta.gov.au/news/")

# Verify each candidate by parsing it (slower, richer metadata).
finder.find_feeds("https://www.dta.gov.au/news/", noverify=False)
# {'url': 'https://www.dta.gov.au/news/',
#  'items': [{'title': 'Digital Transformation Agency',
#             'url': 'https://www.dta.gov.au/feed.xml',
#             'feedtype': 'rss', 'num_entries': 10}]}

# Fall back to HTML extraction when a page has no real feed.
finder.find_feeds("https://government.bg/bg/prestsentar/novini", extractrss=True)

# Include the parsed feed entries in the result.
finder.find_feeds("https://www.dta.gov.au/news/", noverify=False, include_entries=True)
```

You can also render discovered feeds with `newsworker.formats.format_scan`:

```python
from newsworker.formats import format_scan

results = finder.find_feeds("https://www.dta.gov.au/news/", noverify=False)
print(format_scan(results, fmt="opml"))
```

---

## Features

- Identifies news blocks on arbitrary HTML pages using **date patterns** — 340+ patterns via [qddate](https://github.com/ivbeg/qddate).
- Very fast pattern matching built on `pyparsing`.
- Discovers existing RSS/Atom feeds (`scan`), including optional **sitemap.xml** lookup, and falls back to HTML extraction when none exist.
- Multiple output formats for `extract` (JSON, JSON Feed 1.1, RSS, Atom, CSV, HTML, Markdown, YAML) and `scan` (JSON, RSS, Atom, CSV, OPML).
- Reusable YAML **specs** for fast, deterministic re-crawling of known layouts; **site bridges** for host/path overrides.
- **Third-party plugins** via the `newsworker.extractors` entry-point group.
- Local **feed server** with conditional GET (`ETag`/`304`), optional Prometheus metrics, and Docker/Compose deployment.
- **Batch** and **watch** workflows with deduplication, webhooks, and optional async fetching.
- Pattern caching, spec/content caches with CLI management (`cache stats|list|clear`).
- Safe-by-default fetching: TLS verification and `robots.txt` compliance, with per-run overrides, plus proxy/header/cookie/timeout controls.
- Automatic feed-language detection, fuzzy relative-date parsing, and optional per-item **author**, **categories**, and **full-text** enrichment.

---

## Supported languages

Language-specific date recognition currently covers:

Bulgarian · Czech · English · French · German · Portuguese · Russian · Spanish

---

## Performance

- [qddate](https://github.com/ivbeg/qddate) was built specifically for this algorithm; pattern matching is already fast.
- **Cache date patterns** (`cached_p=...`) to reuse the 2–3 patterns found on a site and skip the full pattern set on subsequent runs.
- Prefer **specs** (`analyze` → `extract --spec`) for repeated crawls: deterministic selectors avoid re-running the discovery heuristics.
- Feed discovery without verification (`noverify=True`) is fast; enabling verification parses every candidate and is slower.

---

## Limitations

- Not every language-specific date format is supported yet.
- Right-aligned dates such as `Published - 27-01-2018` are intentionally unsupported — supporting them measurably increases false positives.
- Pages that expose no dates in item text or URLs are not yet supported.

---

## Dependencies

### Runtime

- [qddate](https://pypi.python.org/pypi/qddate) — fast date parsing (the heart of the algorithm).
- [pyparsing](https://pypi.python.org/pypi/pyparsing) — text pattern matching.
- [lxml](https://pypi.python.org/pypi/lxml) + [cssselect](https://pypi.python.org/pypi/cssselect) — HTML parsing and selectors.
- [feedgen](https://github.com/lkiesow/python-feedgen) — RSS/Atom generation.
- [feedparser](https://pypi.python.org/pypi/feedparser) — parsing discovered feeds.
- [typer](https://typer.tiangolo.com/) — the command-line interface.
- [requests](https://pypi.python.org/pypi/requests), [pyyaml](https://pypi.python.org/pypi/PyYAML), [beautifulsoup4](https://pypi.python.org/pypi/beautifulsoup4).

### Optional extras

| Extra | Packages | Enables |
| --- | --- | --- |
| `fulltext` | trafilatura | `extract --full-text` |
| `async` | aiohttp | `batch --async` |
| `metrics` | prometheus_client | `GET /metrics` on the feed server |
| `dev` | pytest, ruff, mypy, pre-commit, build, twine | local development and CI parity |

---

## Documentation

- **Users** — this README (install, CLI, settings, output formats).
- **Developers** — [`docs/README.md`](docs/README.md) (MkDocs Material bootstrap guide),
  [`openspec/`](openspec/) (spec-driven change proposals), and module docstrings in
  `newsworker/`.
- **Performance notes** — [`docs/PERFORMANCE_ANALYSIS.md`](docs/PERFORMANCE_ANALYSIS.md).

Stale Sphinx/autodoc stubs were removed; the README and OpenSpec specs are canonical until
a MkDocs site is adopted (see `docs/README.md`).

---

## Contributing

Issues and pull requests are welcome. Please open an issue to discuss substantial
changes before submitting a PR, and keep additions covered by the changelog.

Development setup:

```bash
pip install -e ".[dev]"     # editable install with dev tools
# or, for a reproducible pinned environment:
pip install -r requirements.txt

pre-commit install          # run ruff/format/whitespace hooks on commit
make test                   # pytest (145+ tests, offline fixtures)
make lint                   # ruff
mypy                        # incremental type checking (see [tool.mypy])
```

Spec-driven changes live under `openspec/`; see `openspec/AGENTS.md` before adding features.

---

## License

Released under the [MIT License](LICENSE). Copyright © Ivan Begtin.

---

## Acknowledgements

This news-extraction code was first written in 2008 and has been refactored several
times — most notably migrating from regular expressions to `pyparsing`. The original
project was later split into two: the [qddate](https://github.com/ivbeg/qddate) date
parsing library and `newsworker` for news identification on HTML pages.

Questions? Reach out at ivan@begtin.tech.

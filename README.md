# newsworker

[![PyPI version](https://img.shields.io/pypi/v/newsworker.svg?style=flat-square)](https://pypi.python.org/pypi/newsworker)
[![Python versions](https://img.shields.io/pypi/pyversions/newsworker.svg?style=flat-square)](https://pypi.python.org/pypi/newsworker)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

> Turn any news page into an RSS/Atom feed — even when the site publishes no feed at all.

`newsworker` is a Python library and command-line tool that **extracts news feeds from plain HTML pages**. It is built for the common case where a site publishes fresh news but offers no RSS/Atom feed, and where generic "page change" monitors are too noisy to be useful. It can also watch many sources and deliver only new items (webhook, e-mail, Telegram, Slack, Discord, Matrix, Mastodon), serve feeds to RSS readers, and give AI assistants news tools over MCP.

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
  - [`explain` — why a page yields what it does](#explain--why-a-page-yields-what-it-does)
  - [`analyze` — generate a reusable spec](#analyze--generate-a-reusable-spec)
  - [`batch` — extract feeds from many pages](#batch--extract-feeds-from-many-pages)
  - [Plugins, bridges and async transport](#plugins-bridges-and-async-transport)
  - [`watch` — poll pages and deliver only new items](#watch--poll-pages-and-deliver-only-new-items)
  - [`history` — export what watch has seen](#history--export-what-watch-has-seen)
  - [`mcp` — news tools for AI assistants](#mcp--news-tools-for-ai-assistants)
  - [`cache` — inspect and manage caches](#cache--inspect-and-manage-caches)
  - [`spec` — validate a parsing spec](#spec--validate-a-parsing-spec)
  - [`parsedate` — inspect date parsing](#parsedate--inspect-date-parsing)
  - [`languages` — what is supported](#languages--what-is-supported)
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

1. **Finds every date** on the page using [qddate](https://github.com/ivbeg/qddate), a fast pattern-based date parser (over 1,000 date and time formats across many languages), plus `<time datetime>` attributes and relative dates such as "3 hours ago" or "вчера".
2. **Clusters** repeated, similarly-structured date nodes to tell apart a *page* date (footer, "last updated") from the *news list* area.
3. **Reconstructs each news item** around its date node, pulling out the title, description, link and image.

The result is a structured feed you can serialize into whatever format you need.

Date clustering is one strategy among several. A URL that already serves RSS, Atom or JSON Feed is read as a feed; plugins and site bridges come next, then cached specs, date clustering, JSON-LD/microdata, and the opt-in undated and browser-rendering fallbacks. `newsworker explain URL` shows which one produced the result and why — see [how it works](docs/docs/getting-started/how-it-works.md).

---

## Installation

Requires **Python 3.10+**.

```bash
pip install newsworker              # runtime
pip install -e ".[dev]"             # editable + pytest, ruff, mypy, pre-commit
pip install newsworker[fulltext]    # optional: trafilatura for --full-text
pip install newsworker[async]       # optional: aiohttp for batch --async
pip install newsworker[browser]     # optional: Playwright rendering via --render
pip install newsworker[metrics]     # optional: Prometheus /metrics endpoint
pip install newsworker[mcp]         # optional: `newsworker mcp` server for AI assistants
```

Installing from source:

```bash
git clone https://github.com/ivbeg/newsworker.git
cd newsworker
pip install -e ".[dev]"
```

### Docker

Run the feed server from the published image (`linux/amd64` and `linux/arm64`).
The server listens on `0.0.0.0:8787` inside the container; publish the port on
loopback only unless you have configured API tokens and an allow-list (see
[Security](docs/docs/guides/security.md)):

```bash
docker run --rm -p 127.0.0.1:8787:8787 -v newsworker-home:/home/newsworker/.newsworker ghcr.io/ivbeg/newsworker
docker run --rm ghcr.io/ivbeg/newsworker extract https://example.com/news -f rss   # any subcommand
```

Build it yourself with `docker build -t newsworker .`.

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

The package installs a single `newsworker` executable exposing these commands:

```text
newsworker [COMMAND] [ARGS] [OPTIONS]

Commands:
  extract    Extract feed records from a web page
  serve      Run a local HTTP server exposing pages as feeds
  feed-url   Print a (signed) subscription URL for the feed server
  explain    Explain why a page yields the items it does (text/HTML report)
  mcp        Serve extract/scan/explain as MCP tools for AI assistants
  history    Export the item history recorded by watch (versions, first/last seen)
  scan       Scan a page and find existing feeds
  analyze    Analyze a page and generate a reusable YAML parsing spec
  batch      Extract feeds from many pages concurrently
  watch      Poll pages (one URL, a list or OPML) and deliver only new items
  cache      Inspect and manage the spec and content caches
  spec       Validate a parsing spec without fetching
  parsedate  Show how extraction reads a date string
  languages  Show the language support matrix
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
| `--user-agent` | | `newsworker/<version> (+URL)` | Override the User-Agent used for fetching. |
| `--language` | | *(auto)* | Override the auto-detected feed language (e.g. `en`, `fr`). |
| `--proxy` | | — | Proxy URL for outgoing requests (e.g. `http://host:port`). |
| `--timeout` | | `30` | HTTP request timeout in seconds. |
| `--header` | | — | Extra HTTP header `Key: Value` (repeatable). |
| `--cookies` | | — | Path to a Netscape/Mozilla cookie jar file. |
| `--insecure` | | `false` | Disable TLS certificate verification for this run. |
| `--legacy-tls-ciphers` | | `false` | Also offer TLS 1.2 ciphers without forward secrecy, for servers that accept nothing else. |
| `--ignore-robots` | | `false` | Fetch even when the site's `robots.txt` disallows it. |
| `--json-logs` | | `false` | Emit logs as structured JSON. |
| `--no-cache` | | `false` | Bypass the spec and content caches for this run. |
| `--refresh` | | `false` | Force re-fetching the page, ignoring cached content. |
| `--fail-on-empty` | | `false` | Exit with status `3` when no items are extracted (useful in cron/CI). |
| `--file` | | — | Extract from a local HTML file instead of a URL (`-` for stdin). |
| `--base-url` | | — | Base URL used to resolve links in local HTML. |
| `--render` | | `false` | Render the page in a headless browser first (`browser` extra). |
| `--undated` | | `false` | Allow the conservative fallback for listings that print no dates. |
| `--explain` / `--explain-json` | | `false` | Print extraction diagnostics to stderr. |
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
| `GET /health`, `/health/live` | Liveness (JSON with the version). |
| `GET /health/ready` | Readiness: cache directory and free feed workers. |
| `GET /metrics` | Prometheus metrics with the `metrics` extra and `metrics_enabled: true`; otherwise `404`. |
| `GET /` | In a browser: a form to paste a page URL, preview its items and copy the feed link. Other clients get short usage help. |

Example — start the server and subscribe from a reader:

```bash
newsworker serve --port 8787
```

Then add this URL to your RSS reader (URL-encode the page URL), or print it with
`newsworker feed-url "https://example.com/news"`:

```text
http://127.0.0.1:8787/feed?url=https%3A%2F%2Fexample.com%2Fnews&format=atom
```

On a shared server, set `feed_signing_key` (and `public_base_url`):
`newsworker feed-url` then prints a signed link that works in readers that
cannot send an API token. See [feed server](docs/docs/integrations/feed-server.md).

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

Scans a page for already-published RSS/Atom feeds (via autodiscovery links, feed icons and link heuristics) and reports them. With `--crawl` it also visits same-site pages, news sections first.

```bash
newsworker scan URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--format` | `-f` | `json` | Output format: `json`, `rss`, `atom`, `csv`, `opml`. |
| `--sitemap` | | `false` | Also discover feed URLs from the site's `/sitemap.xml`. |
| `--no-verify` | | `false` | Return candidates without fetching them for verification. |
| `--max-workers` | | `8` | Candidate feeds verified at the same time. |
| `--fail-on-empty` | | `false` | Exit with status `3` when no feeds are found. |
| `--ignore-robots` | | `false` | Fetch even when the site's `robots.txt` disallows it. |
| `--crawl` | | `false` | Also follow same-site links and look for feeds on those pages. |
| `--max-pages` | | `50` | Pages a crawl fetches at most. Needs `--crawl`. |
| `--max-depth` | | `2` | Link steps a crawl goes from the URL. Needs `--crawl`. |
| `--listings` | | `false` | Also report pages that extraction reads as dated news listings. |
| `--output` | `-o` | *(stdout)* | Write the result to a file instead of printing it. |
| `--config` | `-c` | *(default)* | Path to a settings YAML file. |
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

# Crawl up to 50 same-site pages for feeds and feedless news listings
newsworker scan "https://www.dta.gov.au/" --crawl --listings
```

> **Note:** `scan` verifies every candidate feed by parsing it, so it may take longer than a raw link scan. `feedtype`, `num_entries` and `language` metadata are included where available.

### `explain` — why a page yields what it does

When a feed comes out empty, short or with wrong links, `explain` shows the
evidence: every repeated group of dates on the page and which one won, the
strategies that were tried, the spec a fresh analysis would write, and hints
such as "items link to the listing page itself" or "try --render".

```bash
newsworker explain "https://example.com/news"                  # text summary
newsworker explain "https://example.com/news" -f html -o r.html  # standalone report
```

### `analyze` — generate a reusable spec

Runs the dynamic heuristics once and distills them into a portable **YAML parsing spec**. Feeding that spec back into `extract --spec` skips the expensive analysis step and runs deterministic selectors, which is far faster on repeat crawls of the same layout.

Full spec format, field reference, and analysis pipeline: [parsing specs](docs/docs/guides/parsing-specs.md).

```bash
newsworker analyze URL [OPTIONS]
```

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--output` | `-o` | *(stdout)* | Path to write the YAML spec. |
| `--user-agent` | | `newsworker/<version> (+URL)` | Override the User-Agent used for fetching. |
| `--language` | | *(auto)* | Override the auto-detected feed language (e.g. `en`, `fr`). |
| `--proxy` | | — | Proxy URL for outgoing requests (e.g. `http://host:port`). |
| `--timeout` | | `30` | HTTP request timeout in seconds. |
| `--header` | | — | Extra HTTP header `Key: Value` (repeatable). |
| `--cookies` | | — | Path to a Netscape/Mozilla cookie jar file. |
| `--insecure` | | `false` | Disable TLS certificate verification for this run. |
| `--legacy-tls-ciphers` | | `false` | Also offer TLS 1.2 ciphers without forward secrecy, for servers that accept nothing else. |
| `--ignore-robots` | | `false` | Fetch even when the site's `robots.txt` disallows it. |
| `--json-logs` | | `false` | Emit logs as structured JSON. |
| `--config` | `-c` | *(default)* | Path to a settings YAML file. |
| `--verbose` | `-v` | `false` | Verbose logging. |

`analyze` uses the same fetch settings as `extract`. It records what the dynamic
extractor would choose — including `<time datetime="...">` dates and heading-based
titles — and fails with a clear error when no dated news listings are found.

```bash
newsworker analyze "https://example.com/news" -o example.yaml
newsworker extract "https://example.com/news" -s example.yaml -f rss
```

### `batch` — extract feeds from many pages

Extracts feeds from a list of pages concurrently, writing one file per URL.

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--urls-file` | | — | Text file with one page URL per line. |
| `--from-opml` | | — | OPML file; each outline's `xmlUrl` feed is read and normalised. |
| `--opml-pages` | | `false` | Extract from each outline's `htmlUrl` page instead of its feed. |
| `--output-dir` | `-d` | `.` | Directory for one output file per URL. |
| `--format` | `-f` | `json` | Output format (same set as `extract`). |
| `--max-workers` | | `4` | Concurrent workers (thread pool, or aiohttp when `--async`). |
| `--async` | | `false` | Use the optional aiohttp transport (`newsworker[async]`). |
| `--no-cache` | | `false` | Bypass caches for this run. |
| `--manifest` | | — | Write a per-source manifest (status, items, timings, errors). |
| `--manifest-format` | | `json` | Manifest format: `json` or `csv`. |
| `--failure-policy` | | `strict` | `strict` exits non-zero on any failed source; `partial-success` only when all fail. |
| `--config` | `-c` | *(default)* | Path to settings YAML. |
| `--verbose` | `-v` | `false` | Verbose logging. |

```bash
# One URL per line
newsworker batch --urls-file urls.txt --output-dir out --format rss

# Or normalise a reader's OPML subscriptions (RSS, Atom and JSON Feed) into one format
newsworker batch --from-opml feeds.opml -d out -f json --max-workers 8

# Optional aiohttp transport for high-throughput fetches (install the async extra)
pip install 'newsworker[async]'
newsworker batch --urls-file urls.txt -d out --async
```

### Plugins, bridges and async transport

**Third-party plugins** register extractors via the `newsworker.extractors` setuptools
entry-point group. Each plugin implements `matches(url)` and
`extract(url, data=None, **kwargs)` returning a feed dict (`newsworker.model.Feed`). Matching plugins
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
installed, with the same fetch policy and content cache as the threaded transport;
otherwise the command falls back to the default thread pool.

### `watch` — poll pages and deliver only new items

Polls one page, a list of pages or an OPML file on an interval, tracks which items
it has already seen (in a SQLite store under the cache dir), and emits or delivers
only new items. Every item is also recorded in an item history (`newsworker history`).

| Option | Alias | Default | Description |
| --- | --- | --- | --- |
| `--urls-file` | | — | Watch every URL in a text file (one per line, `#` comments). |
| `--from-opml` | | — | Watch every feed in an OPML file (`--opml-pages` for their `htmlUrl`). |
| `--interval` | `-i` | `300` | Seconds between polls. |
| `--channel` | | `stdout` | Repeatable destination: `stdout`, `webhook`, `smtp`, `telegram`, `slack`, `discord`, `matrix`, `mastodon`. |
| `--webhook` | | — | POST new items as JSON to this URL (with retry/backoff). |
| `--smtp-recipient` | | — | Recipient for the `smtp` channel. |
| `--telegram-chat-id` | | — | Chat for the `telegram` channel. |
| `--format` | `-f` | `json` | Stdout output: JSON Lines for `json`, one document per poll for other formats. |
| `--max-pages` | | `1` | Pages to follow per poll (pagination). |
| `--max-iterations` | | `0` | Stop after N polls (`0` = run until interrupted). |
| `--once` | | `false` | Poll every source once and exit (for cron). |
| `--deliver-updates` | | `false` | Deliver an item again (marked `updated`) when its title, text, link or date changes. |
| `--config` | `-c` | *(default)* | Path to settings YAML. |
| `--verbose` | `-v` | `false` | Verbose logging. |

```bash
# Print new items every 5 minutes
newsworker watch "https://example.com/news" --interval 300

# Watch every feed of a reader's OPML export and post new items to Telegram
newsworker watch --from-opml subscriptions.opml --channel telegram --telegram-chat-id 42

# Deliver new items to a webhook, following pagination
newsworker watch "https://example.com/news" -i 600 --webhook https://hooks.example/new --max-pages 3
```

The loop shuts down cleanly on Ctrl-C / SIGTERM. Use `--once` from cron or
`--max-iterations N` to stop after N polls; a finite run exits with status `1`
when a source could not be fetched or deliveries are still pending. Queued
deliveries are retried before each poll, even while the source is unavailable.
SMTP, Telegram, Slack, Discord, Matrix and Mastodon credentials come from the
settings; see [delivery](docs/docs/guides/delivery.md).

### `history` — export what watch has seen

`watch` records every item with its first and last appearance and a version that
grows when the title, text, link or date changes. Export it as JSON Lines or CSV:

```bash
newsworker history "https://example.com/news" --since 2026-10-01 -f csv -o history.csv
```

Add `--deliver-updates` to `watch` to be notified about edited items.

### `mcp` — news tools for AI assistants

`newsworker mcp` (extra `mcp`) runs a Model Context Protocol server on stdio with
three read-only tools: `extract_news`, `find_feeds` and `explain_page`. They use the
same fetch policy, caches and settings as the CLI. Register it in a client as a
stdio server running `newsworker mcp`; see [MCP server](docs/docs/integrations/mcp.md).

### `cache` — inspect and manage caches

Inspects or clears the spec and content caches (see [Settings and caching](#settings-and-caching)).

```bash
newsworker cache stats            # entry counts and total size per cache
newsworker cache list             # list cached entries
newsworker cache clear            # delete all cached specs and content
newsworker cache clear --content  # scope to a single cache (--specs / --content)
```

### `spec` — validate a parsing spec

Validates a YAML parsing spec without fetching its source URL.

```bash
newsworker spec validate example.yaml
```

### `parsedate` — inspect date parsing

Shows how extraction reads a date string: the qddate pattern and its language,
dateline rewrites, relative dates, the day/month order, precision, offset and
the resulting UTC time. Exits with code 1 when the text is not a date.

```bash
newsworker parsedate "18/06/2018"
newsworker parsedate "05/06/2022" --language en-US --json
newsworker parsedate "3 hours ago" --now 2022-05-06T12:00:00+00:00 --timezone Europe/Moscow
```

### `languages` — what is supported

Prints the evidence-based language matrix: whether dates, page metadata and page
text are recognised for each language, and whether extraction is supported or
partial (`--format text|json|markdown`).

```bash
newsworker languages
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
legacy_tls_ciphers: false        # also offer TLS 1.2 ciphers without forward secrecy
respect_robots: true             # honor robots.txt (incl. Crawl-delay) before fetching
per_host_concurrency: 2          # requests in flight per site, across all workers (0 = unlimited)
per_host_delay: 0                # minimum seconds between requests to one site
max_host_wait: 30                # longest wait for a slot or a Retry-After window (seconds)
request_timeout: 30              # HTTP request timeout (seconds)
proxy: ""                        # proxy URL for outgoing requests ("" = none)
extra_headers: {}                # extra HTTP headers sent with every request
cookies_file: ""                 # optional Netscape/Mozilla cookie jar path
default_language: ""             # feed language override ("" = auto-detect)
bridges_dir: ""                  # user site-bridge YAML dir ("" = ~/.newsworker/bridges)
use_async: false                 # use aiohttp for batch --async (needs [async] extra)
full_text: false                 # follow item links and populate content (needs [fulltext])
full_text_workers: 4             # concurrency for --full-text fetches
structured_data: true            # use JSON-LD / microdata article lists when present
native_feeds: true               # read RSS/Atom/JSON Feed responses as feeds
trust_env_proxy: false           # honor HTTP(S)_PROXY / NO_PROXY / .netrc
history_retention_days: 365      # item history kept by watch (0 = forever)
default_timezone: UTC            # time zone for times printed without an offset
```

Every setting — server access control, delivery channels, rendering and undated
fallbacks — is listed with its default and `NEWSWORKER_*` environment variable in
the [settings reference](docs/docs/guides/settings-reference.md).

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
| `csv`  | Flat table of items: `title, link, pubdate, description, content, content_kind, image, author, categories, unique_id, date_precision`. |
| `html` | A standalone HTML preview page rendering items as cards. |
| `markdown` | A Markdown bulleted list (date, title, link per item). |
| `yaml` | The feed dictionary serialized as YAML (symmetric with the spec format). |

### `scan`

| Format | Description |
| --- | --- |
| `json` | The raw list of discovered feeds. Default. |
| `rss` / `atom` | Each discovered feed becomes an entry (its title and URL), so a feed reader can browse them. |
| `csv`  | Flat table: `title, url, feedtype, num_entries, language, confidence`, plus `found_on` after `--crawl`. |
| `opml` | OPML 2.0 subscription list — the standard interchange format for importing feeds into readers. News listing pages (`--listings`) are left out. |

Publication dates are timezone-aware UTC values. Offsets written on the page
(`<time datetime="…+03:00">`, `10:00 +0300`, `10:00 GMT+3`) are honoured; times
without an offset are interpreted in the `default_timezone` setting (UTC by
default). A date without a time of day keeps its calendar day (00:00 UTC on
that day), and each item says how precise its date is in `date_precision`
(`day`, `minute` or `second`; see
[output formats](docs/docs/guides/output-formats.md#date-precision)). Two-digit years are expanded to the nearest century that is not in the
future, and implausible dates (before 1970 or more than a year ahead) are ignored.

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

`feed` is a dictionary shaped like `newsworker.model.Feed` (a `TypedDict` that documents every key):

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
            "pubdate": datetime.datetime(2018, 6, 18, 0, 0, tzinfo=datetime.timezone.utc),
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

By default requests identify themselves as
`newsworker/<version> (+https://github.com/ivbeg/newsworker)`, so `robots.txt`
rules for `newsworker` apply and site owners can see who is fetching. Override
it per call, with `--user-agent`, or with the `user_agent` setting:

```python
USER_AGENT = "my-monitor/2.0 (+https://example.org/contact)"
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

# Crawl same-site pages too: candidates get found_on, the result a crawl summary.
finder.find_feeds("https://www.dta.gov.au/", crawl=True, max_pages=20)

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

- Identifies news blocks on arbitrary HTML pages using **date patterns** via [qddate](https://github.com/ivbeg/qddate), HTML `<time datetime>` attributes and relative dates in eight languages; datelines (`GENEVA, 29 July 2022`) and day spans are understood.
- Reads **RSS, Atom and JSON Feed** natively and **JSON-LD / microdata** article lists; opt-in fallbacks for undated listings and JavaScript-rendered pages.
- Discovers existing feeds (`scan`): autodiscovery, JSON Feed, sitemaps and WebSub hubs; `--crawl` searches a site's section pages and `--listings` finds feedless news listings.
- Reusable YAML **specs** that heal themselves when a site changes layout, **site bridges** and third-party **plugins**.
- `explain` shows why a page yields what it does; `languages` shows what is supported.
- Output as JSON, JSON Feed 1.1, RSS, Atom, CSV, HTML, Markdown, YAML or OPML.
- **Feed server** with conditional GET, signed links for RSS readers, API tokens, rate limits, a browser form, health checks and optional Prometheus metrics.
- **watch** over one page, a URL list or OPML with a durable outbox, item history and update notifications, delivering to webhooks, e-mail, Telegram, Slack, Discord, Matrix and Mastodon.
- **batch** extraction with manifests and an optional aiohttp transport.
- **MCP server** (`newsworker mcp`) with `extract_news`, `find_feeds` and `explain_page` tools for AI assistants.
- **Safe, polite fetching**: TLS verification, `robots.txt`, private-address blocking checked at connection time, per-host pacing with `Crawl-delay` / `Retry-After`, bounded responses, credentials kept to their origin.
- Docker image on GHCR (`linux/amd64`, `linux/arm64`).

---

## Supported languages

Fixture-backed full date/extraction support currently covers English, French, German,
Italian, Portuguese, Russian, Spanish and Ukrainian, including relative dates such as
"3 hours ago" / "вчера в 14:30". Bulgarian, Czech, and additional script detectors are
partial; run `newsworker languages` or see [language support](docs/docs/guides/language-support.md).

---

## Performance

- [qddate](https://github.com/ivbeg/qddate) was built specifically for this algorithm; pattern matching is already fast.
- **Cache date patterns** (`cached_p=...`) to reuse the 2–3 patterns found on a site and skip the full pattern set on subsequent runs.
- Prefer **specs** (`analyze` → `extract --spec`) for repeated crawls: deterministic selectors avoid re-running the discovery heuristics.
- Feed discovery without verification (`noverify=True`) is fast; enabling verification parses every candidate and is slower.

---

## Limitations

- Not every language-specific date format is supported yet.
- A date after a label is read only when the label is short (up to four words before a comma or a spaced dash, as in `Published - 27-01-2018`); dates inside sentences are not, to keep false positives out.
- Pages that expose no dates at all are handled only by the opt-in, conservative
  `--undated` fallback (repeated cards with titles and links); results carry no
  publication dates.

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
| `browser` | playwright | `extract --render` |
| `metrics` | prometheus_client | `GET /metrics` on the feed server |
| `mcp` | mcp | `newsworker mcp` (Model Context Protocol server) |
| `dev` | pytest, ruff, mypy, pre-commit, build, twine | local development and CI parity |

---

## Documentation

The full documentation site lives in [`docs/`](docs/) (Docusaurus) and is published at
[ivbeg.github.io/newsworker](https://ivbeg.github.io/newsworker/).

```bash
make docs-serve    # local preview (Node.js 18+)
make docs          # production build
```

- [Getting started](docs/docs/getting-started/quick-start.md) — install, first extract, cookbook
- [CLI reference](docs/docs/commands/index.md) — every command and option
- [Parsing specs](docs/docs/guides/parsing-specs.md) — YAML format, field reference, `analyze` pipeline
- [Settings reference](docs/docs/guides/settings-reference.md) — every setting, default and environment variable
- [Runtime configuration](docs/docs/guides/runtime-configuration.md) — CLI / env / YAML precedence
- [Delivery](docs/docs/guides/delivery.md) — watch outbox and channels
- [MCP server](docs/docs/integrations/mcp.md) — tools for AI assistants
- [Upgrading to 1.4](docs/docs/guides/migration-1-4.md) — behaviour changes from 1.3
- [Security](docs/docs/guides/security.md) — fetch policy and server access controls
- [Contributing](docs/docs/development/contributing.md) — local checks and OpenSpec workflow

Spec-driven change proposals remain in [`openspec/`](openspec/).

---

## Contributing

Issues and pull requests are welcome. Please open an issue to discuss substantial
changes before submitting a PR, and keep additions covered by the changelog.

Development setup:

```bash
pip install -e ".[dev]"     # editable install with dev tools
# or, exactly the dependency set CI's `locked` job tests:
pip install -r requirements-lock.txt && pip install --no-deps -e .

pre-commit install          # run ruff/format/whitespace hooks on commit
make test                   # pytest (450+ tests, offline fixtures, 232-page corpus)
make lint                   # ruff format + lint
mypy                        # type-checks the whole package
```

Spec-driven changes live under `openspec/`; see `openspec/AGENTS.md` before adding features.
Documentation changes belong under `docs/docs/`; preview with `make docs-serve`.

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

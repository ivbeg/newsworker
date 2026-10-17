---
title: "Upgrading to 1.4"
description: "Behaviour changes to check when upgrading from 1.3"
---

# Upgrading to 1.4

Most installations upgrade without changes. Check the items below if you run
`watch`, the feed server, `batch --from-opml`, or use newsworker as a library.

## Requirements

- **Python 3.10 or newer** (3.9 reached end of life in October 2025).
- **qddate 1.0.16 or newer** is installed automatically.

## Requests look different to sites

- The **User-Agent** is now `newsworker/<version> (+https://github.com/ivbeg/newsworker)`
  instead of a Chrome 23 string. `robots.txt` rules for `newsworker` now apply.
  Set `user_agent` or `--user-agent` to keep a custom one.
- Requests to one site are **paced**: at most `per_host_concurrency` (default 2)
  at a time, honouring `Crawl-delay` and `Retry-After`. A `batch` over many
  pages of one site can take longer; raise the limit only for sites you own.
- **`HTTP(S)_PROXY`, `NO_PROXY` and `.netrc` are ignored** unless
  `trust_env_proxy: true`. Configure `proxy` explicitly or enable the setting.
- `Authorization`, `Cookie` and your `extra_headers` are **dropped on redirects
  to another origin**, and are never sent to delivery endpoints.

## Feed content

- **`unique_id` comes from the item link**, so editing a teaser no longer makes
  an item "new". The previous text hash is kept as `content_hash`. `watch`
  recognises items seen by 1.3 under their old id, so an upgrade does not
  deliver them again. Feed readers that key on the RSS `guid` may show items
  once more after the upgrade.
- **Publication dates are timezone-aware UTC** `datetime` values. Offsets in
  the page are honoured; other dates use `default_timezone`. Normalise your own
  values before comparing:

  ```python
  from newsworker.tools import normalize_datetime

  same_instant = item["pubdate"] == normalize_datetime(old_value, "Europe/Paris")
  ```

- Dates before 1970 or more than a year ahead are ignored, and two-digit years
  resolve to the nearest past century (`25/7/22` is 2022).
- A URL that serves **RSS, Atom or JSON Feed is read as a feed** (strategy
  `native_feed`). Set `native_feeds: false` to scrape it as HTML as before.
- **JSON-LD and microdata** article lists are used when a page has them
  (`structured_data: false` to disable).
- Full article content carries `content_kind` (`text` or `html`); JSON Feed uses
  `content_text` / `content_html` accordingly. Enclosures are emitted only when
  both the byte length and media type are known.
- `javascript:`, `data:` and other non-http(s) links are removed from items.
- Feed dictionaries are described by `newsworker.model.Feed` / `Item`; plain
  dicts still work.

## Commands

- `batch --from-opml` reads each outline's **feed** (`xmlUrl`); add
  `--opml-pages` to extract from the `htmlUrl` pages as before.
- `scan` of an unreachable page exits with status `1`; `extract` and `scan`
  accept `--fail-on-empty` (status `3`).
- A finite `watch` (`--max-iterations`, `--once`) exits non-zero when a source
  failed or deliveries are still pending.
- `--format rss|atom|…` is honoured by `watch` on stdout.

## Feed server

- With `feed_signing_key` set, `/feed` requires an API token **or** a signed
  link (`newsworker feed-url URL`).
- `?refresh=1` is honoured only for loopback clients and token holders.
- `ETag` is a weak validator over the feed content and `Last-Modified` is the
  newest item date, so readers get `304` for unchanged feeds.
- RSS/Atom `rel="self"` and JSON Feed `feed_url` point to the server's `/feed`
  URL; set `public_base_url` behind a reverse proxy.
- Browsers opening `/` get a form to preview a page and copy its feed link;
  other clients still get the text help.
- `/metrics` needs the `metrics` extra **and** `metrics_enabled: true`.

## Configuration

Precedence is command line, then environment, then YAML, then defaults.
Commands no longer replace a configured User-Agent or filter length when the
matching option is not given. Every setting, its default and environment
variable is listed in the [settings reference](/guides/settings-reference).

## Library

- Importing `newsworker` no longer configures the root logger or silences
  urllib3 warnings; the CLI does that for itself.
- `newsworker.spec` is a package; everything importable before still is.

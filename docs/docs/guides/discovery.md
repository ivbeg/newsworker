---
title: "Feed discovery"
description: "RSS, Atom, JSON Feed, WebSub, and sitemap discovery behaviour"
---

# Modern feed discovery

`newsworker scan` discovers RSS, Atom, and JSON Feed declarations, WebSub
hub/self links, and optionally bounded sitemap URL sets/indexes. Relative URLs
and multi-token `rel` attributes are normalized without losing the declared feed
type or discovery source.

```bash
newsworker scan https://example.com --sitemap --format json
newsworker scan https://example.com --no-verify --format csv
newsworker scan https://example.com --format opml
```

Verification is enabled by default and concurrently fetches bounded candidate
bytes through the shared network policy. Parsers never fetch candidate URLs
themselves. Each JSON/CSV result identifies its source, declared type,
confidence, verification state, and WebSub metadata; OPML/RSS/Atom outputs
retain the normalized candidate URLs.

## Crawling a site

Many sites declare feeds only on section pages (`/news/`, `/press/`, `/blog/`),
not on the home page. `--crawl` follows links from the given URL and runs the
same detectors on every page it visits:

```bash
newsworker scan https://example.com/ --crawl
newsworker scan https://example.com/ --crawl --max-pages 20 --max-depth 1
```

- **Scope**: only http(s) pages on the start page's host; `www.example.com` and
  `example.com` count as one site, other subdomains do not. Fragments are
  dropped and each page is fetched once. Links to PDFs, images, archives,
  office documents, scripts and other non-HTML files are not visited, and
  feed-like links become candidates instead of pages. Feed candidates may point
  to any host.
- **Order**: pages nearer the start come first. At one depth, links whose path
  or text suggests a news section (`news`, `press`, `blog`, `novosti`,
  `новости`, `nachrichten`, `actualités`, `noticias` and more) come before
  other links, and pagination links (`/page/2`, `?page=`) come last.
- **Bounds**: `--max-pages` (default 50) caps requests, failed ones included;
  `--max-depth` (default 2) caps link steps from the start page. Pages are
  fetched one at a time.
- **Politeness**: every page goes through robots.txt (unless
  `--ignore-robots`), `Crawl-delay`, per-host pacing and `Retry-After`. A page
  that fails or is not HTML is skipped and counted; only an unreachable start
  page fails the scan.

The JSON result says where each candidate was found and how the crawl ended:

```json
{
  "url": "https://example.com/",
  "items": [
    {"url": "https://example.com/news/rss", "feedtype": "rss",
     "found_on": ["https://example.com/news/"], "found_on_count": 1}
  ],
  "crawl": {
    "pages_fetched": 37, "max_pages": 50, "max_depth": 2, "truncated": false,
    "skipped": {"robots": 2, "error": 1, "not_html": 4}
  }
}
```

`found_on` keeps the first five pages; a feed in a site-wide header has a
`found_on_count` close to `pages_fetched`. `truncated` is `true` when the crawl
stopped at `--max-pages` with links left.

## News listings without a feed

`--listings` also runs extraction on every scanned page (the start page alone
without `--crawl`) and reports a page with at least three dated items as a
candidate with `feedtype: "html"`, `source: ["extraction"]`, its item count and
the extraction confidence. Extraction uses the page already fetched and your
settings (language, timezone, bridges, plugins) and writes no cache. Turn such a
page into a feed with `extract` or `serve`. OPML output leaves these candidates
out, since a reader cannot subscribe to an HTML page.

```bash
newsworker scan https://example.com/ --crawl --listings -f csv
```

See [`scan`](/commands/scan).

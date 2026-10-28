## Context
`FeedsFinder.find_feeds()` fetches one page, runs `collect_feeds()` on it, optionally
adds `discover_sitemap_feeds()`, merges candidates by normalized URL and verifies them
concurrently. Every fetch goes through `RequestsTransport` with `operation="source"`,
so `HOSTS` pacing, `Retry-After` and `max_host_wait` already apply. Two things the
finder does not do: it never consults robots.txt (that check lives in
`FeedExtractor._can_fetch_policy()` and the async path in `service.py`), and its
`extractrss` path builds a `FeedExtractor()` with default settings.

Constraints from the project: every request goes through `fetch.py`; robots.txt and
per-host pacing apply to crawled pages; discovery stays bounded in pages, bytes and
time; output for existing invocations does not change; no new required dependency.

## Goals / Non-Goals
- Goals:
  - Find feeds declared on section pages of a site from one `scan` call.
  - Optionally find HTML news listings that `extract` can turn into a feed.
  - Stay polite and bounded by default; say where each candidate was found and why
    the crawl stopped.
- Non-Goals:
  - A general site crawler or archive: no article harvesting, no JavaScript
    rendering during the crawl, no resumable crawl state.
  - Crawling subdomains or other hosts (feed candidates may still point anywhere).
  - Seeding the crawl from `sitemap.xml` page URLs (sitemaps list thousands of
    articles; `--sitemap` keeps looking only for feed-like URLs).
  - Crawl options on MCP `find_feeds` or `serve`.
  - Fixing robots.txt for single-page `scan` (separate bug fix).

## Decisions

### Where it lives
The crawl is a loop inside `FeedsFinder.find_feeds()` when `crawl=True`. Single-page
mode keeps its current code path. Candidates from every page are merged with
`_merge_candidates()`, then verified once with the existing thread pool. No new
module: the loop, link scoring and scope checks are a few functions in `finder.py`.

### Queue and order
- Frontier entries: `(depth, -score, discovery_index, url)` in a `heapq`. Lower depth
  first, then higher score, then discovery order, so results are deterministic for a
  given site and bound.
- Visited set keyed by `_normalized(url)` with the fragment removed. The effective URL
  after redirects is also marked visited.
- Stop when the frontier is empty or `max_pages` pages have been fetched. A page whose
  depth equals `max_depth` is scanned for candidates but its links are not queued.
- `truncated` is true when the loop stopped at `max_pages` with entries left.

### Scope
- Same site: the link's host equals the start page's effective host, ignoring one
  leading `www.` on either side, and the scheme is http or https.
- Not visited as pages: feed-like URLs (`_feedlike`), and paths ending in a
  non-HTML extension (`.pdf`, images, audio/video, archives, office documents, `.css`,
  `.js`, `.xml`, `.json`). A fetched page whose `Content-Type` is not HTML/XHTML is
  counted as `not_html` and not parsed.
- Links with `rel="nofollow"` are still followed: nofollow concerns ranking, robots.txt
  is the crawl contract.

### Scoring
`score = hint + shallow` where:
- `hint` is 2 when the URL path or the anchor text contains a section hint
  (`news`, `press`, `blog`, `articles`, `media`, `updates`, `announcements`,
  `novost`, `новости`, `nachrichten`, `actualites`, `noticias`, `notizie` and similar,
  kept as `CRAWL_SECTION_HINTS` in `consts.py`, next to `NEWS_CLASSES_KEYS`), else 0.
- `shallow` is 1 when the path has at most two segments, else 0.
- Pagination links (`/page/N`, `page=`, `p=`, `offset=`, `start=` query parameters)
  get `score = -1`, so they are visited last and mostly fall outside the budget.

This favours section index pages over articles, which is where feeds and listings are
declared. Article pages reached anyway still contribute their header/footer feed links.

### Politeness
- Robots: the logic of `FeedExtractor._can_fetch_policy()` moves to a helper in
  `tools.py` (`robots_allows(url, fetch, agent)`), which reads cached rules through
  `robots_rules()`, applies `Crawl-delay`/`Request-rate` to `HOSTS`, and returns
  whether the URL may be fetched. `extractor.py` and the crawl use it. robots.txt is
  fetched with the finder's transport and policy, capped at 512 KiB as today.
- Pages are fetched sequentially. With one host, parallel page fetches would only
  queue on `per_host_concurrency`, and sequential fetching keeps the order (and tests)
  deterministic.
- Per-page failures (HTTP error, timeout, size cap, policy refusal, `max_host_wait`)
  are logged at debug level, counted as `error` and skipped. An unreachable start
  page returns the existing `{"url", "items": [], "error"}` shape.

### Result shape
In crawl mode:
```json
{
  "url": "https://example.com/",
  "items": [
    {"url": "https://example.com/news/rss", "feedtype": "rss",
     "source": ["autodiscovery"], "found_on": ["https://example.com/news/"],
     "found_on_count": 1, "verification": "valid", "...": "..."}
  ],
  "crawl": {
    "pages_fetched": 37, "max_pages": 50, "max_depth": 2, "truncated": true,
    "skipped": {"robots": 2, "error": 1, "not_html": 4}
  }
}
```
`found_on` keeps the first five pages in visit order; `found_on_count` counts all.
A feed linked from a site-wide header shows a large count, which tells site-wide
feeds from section feeds. Without `--crawl` neither key is emitted.

### News listing candidates (`--listings`)
- For each fetched HTML page, after collecting candidates, run
  `FeedService(settings).get_feed(page_url, data=body)` with one service per scan, so
  the page is not fetched again and the user's settings (language, timezone, specs,
  bridges, plugins) apply.
- Report the page when the feed has at least `MIN_LISTING_ITEMS = 3` items with a
  `pubdate`: `feedtype: "html"`, `source: ["extraction"]`, `num_entries`,
  `confidence` from diagnostics, `verification: "valid"`, title from the feed.
- Listing candidates are not passed to feed verification.
- OPML omits `html` candidates; JSON, CSV, RSS and Atom include them.
- Without `--crawl`, `--listings` runs this on the start page only, which replaces the
  current `extractrss` behaviour (any non-empty feed, default settings).

### CLI
```
newsworker scan URL --crawl [--max-pages 50] [--max-depth 2] [--listings]
```
`--max-pages` and `--max-depth` must be positive and require `--crawl` (exit 2
otherwise). `--max-workers` keeps meaning candidate verification concurrency.
Verbose mode logs each visited page with its depth and score.

## Risks / Trade-offs
- Article pages with "related news" blocks can look like listings →
  `MIN_LISTING_ITEMS`, the scoring that keeps the crawl on section pages, and the
  reported confidence let users filter. The corpus can calibrate the threshold.
- Large sites with slow pages: 50 pages × `request_timeout` is the worst case →
  pages fail fast on `max_host_wait`; a total time bound is an open question.
- `--listings` costs one extraction per page → opt-in, bounded by `--max-pages`.
- Hint words are language-specific → the list covers the languages in
  `language-support`; unmatched sites still crawl breadth-first by depth.

## Migration Plan
Additive. Existing `scan` invocations produce byte-identical output. Library callers
that passed `extractrss=True` get settings-aware extraction and the three-item
threshold; the CHANGELOG notes it.

## Open Questions
- Should the crawl have a total time budget (`--max-time`) in addition to pages and
  depth?
- Should subdomains (`news.example.com` from `example.com`) be an opt-in scope?

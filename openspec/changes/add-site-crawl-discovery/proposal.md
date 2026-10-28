# Change: Discover feeds across a site with a bounded crawl

## Why
`newsworker scan` looks at one page (plus `sitemap.xml` with `--sitemap`). Many sites
declare feeds only on section pages (`/news/`, `/press/`, `/blog/`), not on the home
page, and many have no feed at all but do have news listing pages that `extract` can
turn into one. Finding them today means opening pages by hand and running `scan` or
`extract` on each. Issue #7 (2022) asks for a crawl that does this; `FeedsFinder.find_feeds`
has carried an unused `crawl=False` parameter for it since the initial commit. The
fetch layer now has what a polite crawler needs (one outbound policy, per-host
pacing, `Crawl-delay`, `Retry-After`, bounded responses), so the missing part is
small: a bounded page queue inside one site and rules for which links to follow.

## What Changes
- **`scan --crawl`**: starting at the given URL, `scan` follows same-site links and
  collects feed candidates from every page it visits, with the existing detectors
  (autodiscovery, link heuristics, feed icons, WebSub). No new command: the issue's
  `feedcmd crawl` predates the `newsworker` CLI, and `scan` already has `--output`,
  formats, verification and `--fail-on-empty`.
- **Bounds**: `--max-pages` (default 50) caps pages fetched, `--max-depth`
  (default 2) caps link distance from the start page. Both are usage errors without
  `--crawl`. Pages are fetched one at a time.
- **Link selection**: only http(s) links on the start page's host (`www.` and the bare
  host count as one site); fragments dropped; non-HTML resources and feed-like URLs
  are not visited as pages (feed-like URLs become candidates, as today). Links whose
  URL or anchor text suggest a news section are visited first; pagination links last.
- **Politeness**: in crawl mode every page fetch consults robots.txt when
  `respect_robots` is on (the default) and applies its `Crawl-delay`; disallowed pages
  are skipped. Pacing, `Retry-After` and `max_host_wait` apply as for any source fetch.
  A failing page is counted and skipped; only an unreachable start page fails the scan.
- **Provenance and summary**: in crawl mode each candidate lists the pages it was
  found on (`found_on`, first five, plus `found_on_count`), and the JSON result gains
  a `crawl` object (pages fetched, pages skipped by reason, bounds, whether the crawl
  stopped at a bound with links left). CSV gains a trailing `found_on` column in crawl
  mode. Results without `--crawl` are unchanged.
- **`scan --listings`** (opt-in, with or without `--crawl`): pages that `extract` can
  read as a dated news listing (at least three dated items) are reported as
  candidates with `feedtype: "html"` and `source: ["extraction"]`, the extraction
  confidence and item count. Extraction reuses the fetched body through
  `FeedService.get_feed(data=...)` and the user's settings. OPML output leaves these
  candidates out, since an HTML page is not a subscription.
- **Library**: `FeedsFinder.find_feeds(url, crawl=True, max_pages=..., max_depth=...)`
  gives the stub parameter its meaning; `extractrss=True` becomes the library form of
  `--listings` and goes through `FeedService` instead of a default-settings
  `FeedExtractor`.

## Impact
- Affected specs: `feed-discovery` (new requirements: bounded site crawl, crawl link
  selection, crawl politeness, crawl provenance and summary, news listing candidates).
- Affected code: `newsworker/finder.py` (crawl loop, link selection, provenance,
  listings through `FeedService`), `newsworker/tools.py` (robots check shared with
  `extractor.py`), `newsworker/extractor.py` (uses the shared helper),
  `newsworker/consts.py` (section hints), `newsworker/formats.py` (CSV `found_on`,
  OPML skips `html` candidates), `newsworker/core.py` (`--crawl`, `--max-pages`,
  `--max-depth`, `--listings` on `scan`), docs (`commands/scan.md`,
  `guides/discovery.md`, `use-cases/feed-discovery.md`, README), CHANGELOG.
- No new dependency. No new settings: the bounds are per-run options.
- MCP `find_feeds` and `serve` are unchanged; crawling from an assistant tool call is
  left for a later change once costs are known.
- Single-page `scan` does not consult robots.txt today. That gap is a bug against the
  network fetch policy and is fixed separately; crawl mode checks robots from the start.
- Closes ivbeg/newsworker#7.

# Change: Sitemap discovery, OPML import, and batch extraction

## Why
`newsworker` is an island: `scan` does not consult `sitemap.xml`, there is no way to feed
it an OPML subscription list, and there is no batch command despite the library already
having concurrent `FeedService.get_feeds`. These make it a credible crawl-and-deliver
component. (Audit E1, E10, B10.)

## What Changes
- `scan` discovers feeds via `/sitemap.xml`: fetch and parse it with lxml, surfacing URLs
  that look like feeds (`.rss`/`.atom`) or news sections.
- `scan --from-opml subs.opml`: iterate OPML outlines and scan each entry.
- `newsworker batch-feeds feeds.opml -o out/`: extract a feed per OPML outline into a
  directory, reusing the concurrent `FeedService.get_feeds`.

## Impact
- Affected specs: `feed-discovery`
- Affected code: `finder.py` (sitemap parsing), `core.py` (`scan` options, new
  `batch-feeds` command), a small OPML reader helper in `formats.py` or `tools.py`

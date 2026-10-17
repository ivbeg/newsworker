## 1. Sitemap discovery
- [x] 1.1 Add `discover_sitemap_feeds(base_url)` fetching/parsing `/sitemap.xml`
- [x] 1.2 Collect `<loc>` URLs that look like feeds (`.rss`/`.atom`, `/feed`, `/rss`)
- [x] 1.3 Merge sitemap results into `scan` output behind `--sitemap`
- [x] 1.4 Be lenient when the sitemap is missing/malformed (return empty)

## 2. OPML import
- [x] 2.1 Add `read_opml(path_or_str)` returning `[{title, url, html_url}]`
- [x] 2.2 Skip outlines without an `xmlUrl`

## 3. Batch extraction
- [x] 3.1 Add a `batch` CLI command reading URLs from `--urls-file` or `--from-opml`
- [x] 3.2 Use `FeedService.get_feeds` (concurrent) and write one file per URL to `--output-dir`
- [x] 3.3 Isolate per-URL failures (skip with a warning, keep going)

## 4. Tests & docs
- [x] 4.1 Test sitemap parsing on a fixture (and missing-sitemap leniency)
- [x] 4.2 Test OPML import from string and file
- [x] 4.3 Test the `batch` command writes one file per URL
- [x] 4.4 Document `scan --sitemap` and `batch` in README

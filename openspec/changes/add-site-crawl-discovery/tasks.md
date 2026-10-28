## 1. Robots helper
- [ ] 1.1 `tools.py`: `robots_allows(url, fetch, agent)` from `FeedExtractor._can_fetch_policy()` (cached rules, `Crawl-delay`/`Request-rate` to `HOSTS`, lenient on unreadable robots.txt)
- [ ] 1.2 `extractor.py`: use the helper; existing robots and pacing tests stay green

## 2. Crawl loop
- [ ] 2.1 `consts.py`: `CRAWL_SECTION_HINTS`, non-HTML extensions, pagination markers
- [ ] 2.2 `finder.py`: scope check (same host, `www.` alias, http/https), fragment removal, link scoring, pagination demotion
- [ ] 2.3 `finder.py`: `find_feeds(crawl=True, max_pages=50, max_depth=2)` with heap frontier, visited set incl. effective URLs, depth bound, sequential fetches, robots check per page, `not_html`/`error`/`robots` counters, `truncated`
- [ ] 2.4 `finder.py`: `found_on`/`found_on_count` provenance merged across pages; `crawl` summary in the result; single-page output unchanged
- [ ] 2.5 Tests with a fake transport: section page feed found, depth bound, page bound and `truncated`, cycle, off-host link ignored, `www.` alias, PDF/image links skipped, non-HTML response counted, robots-disallowed page skipped and `Crawl-delay` noted, failing page isolated, unreachable start page error, deterministic order, feed-like link not visited

## 3. News listings
- [ ] 3.1 `finder.py`: listing check through `FeedService.get_feed(url, data=body)` with one service per scan; `MIN_LISTING_ITEMS = 3` dated items; `feedtype: "html"`, `source: ["extraction"]`, confidence, item count; not verified as a feed
- [ ] 3.2 `extractrss=True` uses the same path (start page only without crawl)
- [ ] 3.3 Tests: listing page reported, article page with two dated related links not reported, settings language passed through, no second fetch of the page

## 4. Output
- [ ] 4.1 `formats.py`: CSV trailing `found_on` column (first page) only when the result has `crawl`; OPML skips `html` candidates
- [ ] 4.2 Tests: CSV header unchanged without crawl, OPML without listings, JSON `crawl` object

## 5. CLI
- [ ] 5.1 `core.py`: `scan --crawl`, `--max-pages`, `--max-depth`, `--listings`; positive values; `--max-pages`/`--max-depth` without `--crawl` exit 2; verbose per-page log
- [ ] 5.2 CLI tests: option validation, `--fail-on-empty` with a crawl, `--output` with a crawl

## 6. Documentation and release
- [ ] 6.1 `docs/docs/commands/scan.md` option table; `guides/discovery.md` crawl section (scope, order, bounds, robots, listings); `use-cases/feed-discovery.md` example; README feature list
- [ ] 6.2 CHANGELOG entry, including the `extractrss` behaviour change
- [ ] 6.3 Live check of a few sites from `benchmarks/live_sources.json` with `--crawl --listings` (pages fetched, candidates, time)
- [ ] 6.4 `openspec validate add-site-crawl-discovery --strict`, ruff, mypy, full test suite

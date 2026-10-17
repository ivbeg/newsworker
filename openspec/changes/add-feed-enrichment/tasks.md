## 0. Prerequisite
- [ ] 0.1 Land the formats fix: Atom keeps full `content` next to `summary`, RSS emits `dc:creator` (bug fix, no spec change)

## 1. Model
- [ ] 1.1 `model.py`: add `Item.authors`, `Item.modified`, `Item.source_hash`; `ItemExtra.enclosures`, `ItemExtra.enriched`, `ItemExtra.canonical_url`; `Enclosure` TypedDict; `Feed.image`
- [ ] 1.2 Extend `tests/test_model.py` to cover the new keys from native and enriched feeds

## 2. Native feed fidelity
- [ ] 2.1 `native.py`: map all enclosures, `media_content`, `media_thumbnail`, `authors`, `modified`, feed image (feedparser path)
- [ ] 2.2 `native.py`: JSON Feed `attachments`, `date_modified`, `authors`, `icon`/`favicon`
- [ ] 2.3 Fixtures and tests: podcast RSS, Media RSS, multi-author `dc:creator`, Atom published/updated, enclosure with `length="0"`, JSON Feed attachments

## 3. Rendering
- [ ] 3.1 `formats.py`: load feedgen `dc` and `media` extensions; RSS `<enclosure>` selection, `media:content`, `media:thumbnail`, one `dc:creator` per author, channel `<image>`
- [ ] 3.2 `formats.py`: Atom `link rel="enclosure"` per enclosure, one `<author>` per author, `<published>`/`<updated>` from pubdate/modified, `<logo>`
- [ ] 3.3 `formats.py`: JSON Feed `attachments`, `authors`, `date_modified`, `icon`; CSV/HTML/Markdown show all authors
- [ ] 3.4 Feed-level update time from the newest pubdate or modified; keep `content_fingerprint` stable for unchanged feeds
- [ ] 3.5 `keep_native_ids` setting and rendering of `native_id` as guid/id
- [ ] 3.6 Tests: podcast round trip (rss→rss, rss→atom, rss→jsonfeed), unknown-length enclosure, two authors per format, modified dates, feed image, native ids on/off

## 4. Article stage
- [ ] 4.1 `enrich.py`: `ArticleDocument`, `Fill`, `BaseEnricherPlugin`, `FILLABLE_FIELDS`, missing-field rules and the runner (order, first-fill-wins, declared-field filter, per-enricher error isolation, provenance)
- [ ] 4.2 `service.py`: `_enrich_articles()` with candidate selection, skip rule, `enrich_max_items`, fetch through `_fetch` (content cache, single-flight, `--refresh`), HTML content-type check, `full_text_workers` concurrency, aggregated warning
- [ ] 4.3 `service.py`: pipeline order (`source_hash` before the stage, `sanitize_feed_links` after it), `provenance.enrichers`, `diagnostics.metadata["enrichment"]`; show it in `explain`
- [ ] 4.4 Move full text onto the stage as the built-in `fulltext` enricher; remove `_add_full_text()`; `--full-text`/`full_text` add `fulltext`; keep the missing-dependency error
- [ ] 4.5 Tests with a fake transport: one fetch per link with two enrichers, cache hit on rebuild, robots-disallowed article, PDF link, complete native bodies not fetched, teaser replaced, budget cut-off, byte-identical rebuild

## 5. Metadata enricher
- [ ] 5.1 `structured.py`: expose the JSON-LD helpers for reuse without changing listing behaviour
- [ ] 5.2 `enrich.py`: `metadata` enricher — JSON-LD article-node selection, OpenGraph/`article:*`, meta tags, precedence, date plausibility, URL safety, value normalisation and caps
- [ ] 5.3 Redirect unwrap of `link` and `extra.canonical_url`; `unique_id` unchanged
- [ ] 5.4 Boilerplate guard for site-wide description/image
- [ ] 5.5 Tests: undated item gets a date, unmatched multiple JSON-LD nodes, implausible date, tracking redirect, site-wide `og:description`, `og:image` without enclosure, source values never overwritten, provenance labels
- [ ] 5.6 Corpus check: enrichment off by default leaves `tests/corpus` scores unchanged

## 6. Plugins
- [ ] 6.1 `newsworker.enrichers` entry-point discovery, lazy loading, run only when named, `plugin:<name>` provenance
- [ ] 6.2 Tests: installed-but-unselected, declared fill applied, undeclared fill ignored, raising plugin isolated

## 7. Settings and CLI
- [ ] 7.1 `settings.py`: `enrich`, `enrich_max_items`, `enrich_min_content_chars`, `keep_native_ids`; early validation of enricher names; environment variables
- [ ] 7.2 `settings_doc.py` entries and regenerated settings reference
- [ ] 7.3 `core.py`: `--enrich` on `extract`, `batch`, `watch`, `serve`; CLI reference pages updated and checked by tests

## 8. Watch stability
- [ ] 8.1 `dedup.py`: version on `source_hash` when present; accept the previous full-item hash as the same version and rewrite it
- [ ] 8.2 Tests: enabling enrichment on an existing history, varying full text, real title edit still versions

## 9. Documentation and release
- [ ] 9.1 New guide `docs/docs/guides/enrichment.md` (feed proxy use case, enrichers, budget, provenance, plugin protocol); update `output-formats.md`, `python-library.md`, `plugins-and-bridges.md`, README feature list
- [ ] 9.2 CHANGELOG entry, including the first-author change for multi-author native entries and full text no longer replacing complete native bodies
- [ ] 9.3 Benchmark the article stage with `benchmarks/runtime_benchmark.py` (cached rebuild of a 30-item feed)
- [ ] 9.4 `openspec validate add-feed-enrichment --strict`, ruff, mypy, full test suite

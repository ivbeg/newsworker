# Change: Enrich feeds from their article pages and keep native feeds intact

## Why
newsworker already reads a feed URL and re-renders it (`extract FEED_URL --full-text`,
`serve` with `full_text: true`), which makes it a natural "feed in, better feed out"
proxy. Today that path loses data and wastes fetches: podcast enclosures, Media RSS
thumbnails, all but one author, modification dates and the channel image are dropped
by `native.py`; full text overwrites complete `content:encoded` bodies, bypasses the
content cache (every `/feed` rebuild re-fetches every article), and throws away the
article HTML after taking its text, although that page carries exact dates, images,
authors and sections the listing lacks. Undated items in particular could get real
dates from the article they link to.

## What Changes
- **Native feed fidelity**: keep enclosures (any media type, with declared type and
  length), Media RSS `media:content` / `media:thumbnail`, every author, the `updated`
  date separately from `published`, the channel image, and offer the publisher's entry
  id as the rendered guid/id (`keep_native_ids`, opt-in).
- **Article fetch stage**: one fetch per item link per build, through the content cache
  and the outbound fetch policy, shared by every enricher that needs the article page.
  Items whose fields are already complete are skipped (`enrich_min_content_chars`),
  and a per-build cap (`enrich_max_items`) bounds the cost.
- **Enricher selection**: `enrich` setting and `--enrich` option name the enrichers to
  run, in order. `--full-text` / `full_text: true` become an alias for adding the
  built-in `fulltext` enricher; full text no longer replaces native content that is
  already long enough.
- **`metadata` enricher (Tier 1)**: deterministic fill of missing `pubdate`, `modified`,
  `author`/`authors`, `categories`, `description` and image from the article's JSON-LD,
  OpenGraph/`article:*` and standard meta tags; redirect-unwrapped item links; the
  canonical URL recorded. Values are only added where the item has none, and nothing
  is fabricated.
- **Provenance**: each enriched field records its source in `extra.enriched`
  (`json-ld`, `opengraph`, `meta`, `redirect`, `trafilatura`, `readability`,
  `plugin:<name>`); the feed lists the enrichers that ran.
- **Enricher plugins**: a `newsworker.enrichers` entry-point group with a small
  protocol; plugins run only when named in `enrich`, receive the already-fetched
  article, may only fill declared fields and are isolated from each other's failures.
- **Output**: RSS/Atom/JSON Feed render enclosures, Media RSS, several authors,
  modification dates and the feed image.
- **Watch stability**: item versions are computed from publisher-provided values, so
  enabling enrichment or a varying article extraction does not create new versions.
- Behaviour change: for a native entry with several authors, `author` becomes the first
  author (feedparser currently yields the last); `authors` holds all of them.

## Impact
- Affected specs: `feed-enrichment` (new), `feed-extraction` (Native Feed Passthrough,
  Full-article Body Extraction), `output-contracts`, `watch-delivery-reliability`.
- Affected code: `newsworker/enrich.py` (runner, protocol, built-ins), `native.py`,
  `service.py` (`get_feed`, `_add_full_text` replaced by the article stage),
  `structured.py` (shared JSON-LD helpers), `formats.py`, `model.py`, `dedup.py`,
  `settings.py` + `settings_doc.py`, `core.py` (`--enrich` on `extract`, `batch`,
  `watch`), docs (`guides/output-formats.md`, a new enrichment guide, settings and CLI
  reference).
- No new required dependency: feedgen's bundled `dc` and `media` extensions cover the
  new output elements; `fulltext` keeps using the existing `fulltext` extra.
- Builds on the formats fix that makes Atom keep full `content` next to `summary` and
  RSS emit `dc:creator` (bug fix, tracked separately, no spec change).
- `serve` and MCP pick enrichment up from settings; `/feed` request parameters and the
  link signature are unchanged.

## Context
Every strategy ends in the same tail of `FeedService.get_feed()`: links are sanitised,
identities assigned, `enrich_feed()` reads author/categories from the item's
`raw_html`, and `_add_full_text()` optionally fetches each item link. That tail is the
right place for enrichment because it is shared by native feeds, specs, heuristics,
structured data and the undated fallback. Two facts shape the design:

- Native feed items have no `raw_html`, so the existing enrichment does nothing for
  them; the only extra information available is on the article page.
- `_add_full_text()` calls `extractor.fetch()` directly (no content cache, no
  single-flight) and discards the HTML after text extraction, so a server rebuilding a
  feed fetches every article again and gains nothing beyond the body text.

Project constraints that apply: every request goes through `fetch.py`; robots.txt and
per-host pacing apply; enclosure metadata is never fabricated; only content-derived
facts go into the feed so unchanged inputs render to identical bytes; optional features
stay behind extras; the HTTP server stays dependency-free.

## Goals / Non-Goals
- Goals:
  - Feed in, richer feed out, without losing anything the source feed carried.
  - One bounded, cached article fetch per item, shared by all enrichers.
  - Deterministic Tier 1 metadata from the article page, filling only gaps, with
    per-field provenance.
  - A small plugin protocol so NLP or model-based enrichers can live outside core.
- Non-Goals:
  - Model-based summaries, translation, classification or NER in core (plugins).
  - Overwriting publisher values, including truncated titles (later change).
  - Per-request enrichment options on `/feed` (needs a signature change and lets
    anonymous clients multiply fetch cost).
  - HEAD/range probing for enclosure length or type.
  - Merging several source feeds into one, or cross-feed near-duplicate detection.

## Decisions

### Pipeline order
```
strategy → sanitize_feed_links → assign_item_identities → enrich_feed (raw_html)
        → source_hash (when enrich is non-empty) → article stage → sanitize_feed_links
        → provenance
```
The article stage runs after identities, so `unique_id` never depends on enrichment.
Links and images added by enrichers pass through `sanitize_feed_links` again.

### Article stage (`FeedService._enrich_articles`)
- Candidates: items with a safe http(s) link that differs from the feed's page URL,
  de-duplicated by link within the build.
- Skip rule: an item is fetched only when at least one selected enricher with
  `needs_article = True` declares a field that is missing on the item (definitions
  below). Complete native items cost nothing.
- Budget: `enrich_max_items` (0 = no cap) counts candidates that pass the skip rule,
  in feed order; the rest are left as they are and counted in diagnostics.
- Fetch: `self._fetch(link, force_refresh=..., context=new_context(source="article"))`,
  i.e. content cache (`content_ttl`), single-flight, robots.txt, size cap, SSRF policy
  and per-host pacing. `--refresh` propagates. Concurrency reuses `full_text_workers`.
- Responses whose `Content-Type` is not HTML/XHTML produce no article document.
- Failures (robots, HTTP, size, timeout) leave the item unchanged and add one
  aggregated warning: `Enrichment unavailable for N of M item(s)`.
- `fetch_article` is passed into the runner in `enrich.py` as a callable, so
  `enrich.py` stays independent of the service.

### Article document
```python
@dataclass(frozen=True)
class ArticleDocument:
    url: str                 # item link that was requested
    effective_url: str       # after redirects
    data: bytes
    content_type: str | None
    language: str | None     # Content-Language or <html lang>

    @cached_property
    def tree(self): ...      # lxml document, parsed once, shared by enrichers

    @cached_property
    def json_ld(self): ...   # decoded JSON-LD nodes, via structured.py helpers
```

### Enricher protocol and selection
```python
class Fill(NamedTuple):
    field: str    # one of FILLABLE_FIELDS
    value: Any
    source: str   # provenance label, e.g. "json-ld"

class BaseEnricherPlugin:
    name: str = ""                       # key used in the `enrich` setting
    fields: frozenset[str] = frozenset() # fields it may fill
    needs_article: bool = True

    def enrich(self, item: Item, article: ArticleDocument | None) -> Iterable[Fill]:
        raise NotImplementedError
```
- `FILLABLE_FIELDS = {"description", "pubdate", "modified", "author", "authors",
  "categories", "content", "image"}`. `content` carries `(text, kind)`; `image` appends
  to `extra.images`; filling `authors` also sets `author` to the first one when absent.
- Identity and source fields (`unique_id`, `content_hash`, `native_id`, `link`,
  `raw_html`, `title`) are not fillable. Only the built-in `metadata` enricher may set
  `link`, and only from a redirect (below).
- Built-ins `metadata` and `fulltext` are registered in the same registry as plugins;
  third-party enrichers come from the `newsworker.enrichers` entry-point group and are
  loaded lazily the first time a name in `enrich` is not built in.
- Enrichers run in `enrich` order per item; the first fill of a field wins.
  `--full-text` / `full_text: true` append `fulltext` when not already listed.
- Unknown names fail early configuration validation, listing the available names.
- A Fill for an undeclared field is dropped with a debug log; an exception from one
  enricher skips that enricher for that item, records a warning and lets the others run.
- Third-party fills are recorded as `plugin:<name>`; built-ins record their own source.
- Plugins receive the fetched document and no network client; doing their own network
  I/O is outside the contract (documented, not enforced in-process).

### Missing-field definitions (fill-only-missing)
- `pubdate`, `modified`: `None`.
- `author`, `authors`, `categories`: absent or empty.
- `description`: empty, or equal to `title` after whitespace normalisation (native
  feeds and HTML strategies fall back to the title).
- `content`: absent, or plain-text length below `enrich_min_content_chars` (default 500),
  so a teaser in `content:encoded` can be replaced by full text but a complete body
  is kept.
- `image`: `extra.images` empty.

### `metadata` enricher
- Sources, highest precedence first, per field:
  1. JSON-LD: the article node (types from `structured.ARTICLE_TYPES` except `event`)
     whose `url`, `@id` or `mainEntityOfPage` matches the effective or canonical URL,
     else the only article node on the page; several unmatched nodes → JSON-LD unused.
     `datePublished`, `dateModified`, `author` (string, Person, list), `image` (string,
     ImageObject, list), `articleSection` + `keywords`, `description`.
  2. OpenGraph/`article:*`: `article:published_time`, `article:modified_time`,
     `article:author` (names only, URLs ignored), `article:section`, `article:tag`,
     `og:image` (`og:image:secure_url` preferred), `og:description`.
  3. Meta: `name=author`, `name=description`, `name=keywords` (comma-separated).
- `structured.py` keeps listing semantics (`extract_structured_items` excludes the page
  itself); the enricher reuses its private helpers (`_json_ld_documents`, `_walk`,
  `_types`, `_text`, `_url`), which become module-level shared helpers.
- Dates use `parse_datetime_attr(default_timezone=...)` and the existing plausibility
  window (not before 1970, not more than one year ahead).
- URLs are absolutised against `effective_url` and must pass `is_safe_link`.
- Text values are whitespace-normalised and capped (author 200, category 100,
  description 2000 characters); HTML in values is reduced to text.
- Redirect unwrap: when the fetch ended on a different URL than the item link (after
  `clean_url`), `link` becomes the cleaned effective URL with provenance `redirect`
  (feedproxy, tracking redirects). `unique_id` keeps its original value.
- Canonical: `<link rel=canonical>` is recorded as `extra.canonical_url` when it differs
  from the final link; it never replaces `link`, because sites point it at aggregators
  or home pages.
- Boilerplate guard: after the stage, a `description` or `image` value the enricher
  applied to at least 3 items and at least half of the enriched items of the build is
  reverted (site-wide `og:description` or logo `og:image`).

### `fulltext` enricher
Wraps `extract_fulltext_with_kind()`: trafilatura text, readability HTML fallback,
same extras and error message when neither is installed. Declares `content`.
Provenance `trafilatura` or `readability`.

### Data model (`model.py`)
- `Item`: `authors: list[str]`, `modified: dt.datetime | None`, `source_hash: str`.
- `ItemExtra`: `enclosures: list[Enclosure]`, `enriched: dict[str, str]`,
  `canonical_url: str`; existing `links`/`images` unchanged.
- `Enclosure(TypedDict, total=False)`: `url`, `type`, `length`, `medium`.
- `Feed`: `image: str`; `provenance["enrichers"]: list[str]`.
- The HTML-derived `extra.enclosure_type` / `enclosure_length` keep working; renderers
  read them as an enclosure for the first image, as today.

### Native feed mapping (`native.py`)
- `entry.enclosures` → `extra.enclosures` (`type` lower-cased, `length` as int when
  declared and positive, else `None`); `image/*` enclosures also go to `extra.images`.
- `media_content` → `extra.enclosures` (`fileSize` → `length`, `medium`); image media
  also to `extra.images`. `media_thumbnail` → `extra.images`.
- `entry.authors` names in order, de-duplicated → `authors`; `author` = first.
- `pubdate` = published, else updated; `modified` = updated when it differs from
  `pubdate`.
- Feed image: `feed.image.href`, else `feed.logo`, else `feed.icon`.
- JSON Feed: `attachments` → enclosures, `date_modified` → `modified`, all `authors`,
  `icon`/`favicon` → feed image.

### Rendering (`formats.py`)
- Load feedgen's `dc` and `media` extensions.
- RSS: one `<enclosure>` — the first enclosure with both type and length, audio/video
  before others, then the existing image path; `media:content` per enclosure with the
  attributes that are known; `media:thumbnail` for the first image; `dc:creator` per
  author; channel `<image>` from the feed image.
- Atom: `link rel="enclosure"` per enclosure with type and length; `<author>` per
  author; `<published>` = pubdate, `<updated>` = modified or pubdate; `<logo>`.
- JSON Feed: `attachments` for enclosures with type and length; `authors`;
  `date_modified`; `icon`.
- Feed-level `updated`/`lastBuildDate` use the newest of pubdate and modified.
- `keep_native_ids`: RSS `<guid>` and Atom `<id>` use `native_id` when present
  (`isPermaLink="true"` only when it equals the item link). Internal `unique_id`, watch
  identity and dedup are unchanged. Off by default because changing emitted ids makes
  existing subscribers see every item again.

### Watch stability (`dedup.py`)
When `enrich` is non-empty the service stores `source_hash = DedupStore.content_hash(item)`
before the article stage. `record_items` versions on `source_hash` when present.
For history rows written before this change (full text was part of the hash), a
stored hash equal to either `source_hash` or the full `content_hash(item)` counts as
the same version and is rewritten to `source_hash` silently.

### Diagnostics
`diagnostics.metadata["enrichment"] = {"selected", "fetched", "cached", "skipped",
"over_budget", "failed"}` and per-enricher error counts; shown by `explain`. These stay
out of the feed (they vary with cache state); the feed carries only
`provenance.enrichers` and the aggregated warning, as full text does today.

## Alternatives considered
- Enrichment inside each strategy: duplicates logic and misses native feeds.
- A separate `enrich` command: a second pipeline; `--enrich` on existing commands keeps
  one code path (`extract FEED_URL --enrich metadata,fulltext -f atom`).
- Configurable overwrite policy: makes output depend on flags in surprising ways;
  fill-only keeps the publisher authoritative.
- Auto-running installed enrichers like extractors: enrichers change every feed, so
  they must be named explicitly.
- A derived-result cache (parsed metadata per link): deferred until the runtime
  benchmark shows parsing cost matters; the content cache already removes network cost.

## Risks / Trade-offs
- Fetch amplification (N article fetches per build) → off by default, skip rule,
  `enrich_max_items`, content cache, robots.txt, per-host pacing.
- Wrong page-level metadata (site-wide description, logo as image, aggregator canonical)
  → fill only gaps, strict JSON-LD node matching, boilerplate guard, canonical recorded
  but not applied.
- Hostile article HTML → bounded by `max_content_bytes`, text-only values, `is_safe_link`
  for URLs, link sanitising after the stage; previews already escape values.
- Cached articles within `content_ttl` hide later edits → `--refresh`; possible
  separate `article_ttl` (open question).
- `source_hash` means full-text-only edits no longer create watch versions → documented;
  title, description, link, date and native content edits still do.
- Plugins can be slow or misbehave → per-item isolation and warnings; no in-process
  timeout in this change.

## Migration Plan
1. Native fidelity and rendering (additive keys; `author` first-author change noted in
   CHANGELOG and the 1.x migration guide).
2. Article stage with `fulltext` moved onto it; `--full-text` keeps working; full text
   stops replacing complete native bodies and becomes cached.
3. `metadata` enricher, provenance, `source_hash`.
4. Plugin group and documentation.
Rollback: leave `enrich` empty and `full_text` false — the article stage does not run
and output matches the previous release apart from the native-feed additions.

## Open Questions
- Separate `article_ttl`, given articles change less often than listings?
- RSS requires `length` on `<enclosure>`; podcast feeds that declare none lose the RSS
  enclosure under the truthful-metadata rule (the item keeps `media:content`). Accept, or
  allow passing through a publisher-declared `length="0"`?
- Should `watch` enrich only items not yet in item history (needs a dedup lookup from
  the service)?
- Per-item `language` from the article (`inLanguage`, `<html lang>`) — new item field?

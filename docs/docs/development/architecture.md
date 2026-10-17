---
title: "Architecture"
description: "Module map and data flow from fetch through extraction to output"
---

# Architecture

newsworker is a thin CLI layer (`core.py`) over a service layer (`service.py`).
The service picks an extraction strategy per page; the modules below own one
concern each.

| Module | Role |
|--------|------|
| `service.py` | `FeedService`: caching, strategy order, pagination, enrichment, batch |
| `fetch.py` | Outbound policy: address checks at connect time, redirects, credentials, size limits, per-host pacing (`HostScheduler`) |
| `runtime.py` | Request-scoped `ExtractionContext` and single-flight coalescing |
| `extractor.py` | Dynamic date-driven extraction (date clusters → item blocks) |
| `dates.py` / `relative.py` | qddate matches → plausible UTC instants; relative dates in 8 languages |
| `structured.py` | JSON-LD and microdata article lists |
| `native.py` | RSS, Atom and JSON Feed responses normalised to the item contract |
| `undated.py` | Opt-in undated listing fallback |
| `spec/model.py` | The YAML spec (`FeedSpec`, `FieldRule`, `ItemsRule`) and its validation |
| `spec/selectors.py` | Building CSS/XPath selectors from elements and evaluating them |
| `spec/analyze.py` | `SpecAnalyzer`: page → spec, using the dynamic heuristics once |
| `spec/execute.py` | `SpecExtractor`: spec → items with deterministic selectors |
| `cache.py` | SHA-1-keyed file caches for specs and page content |
| `finder.py` | Discovers existing feeds via autodiscovery, icons and sitemaps |
| `formats.py` | Renders the feed dict to json/rss/atom/csv/jsonfeed/html/markdown/yaml/opml |
| `server.py` | Stdlib HTTP server: `/feed` (tokens or signed links), health, metrics |
| `watching.py` | One `watch` poll: drain due deliveries, fetch, enqueue and deliver |
| `dedup.py` / `delivery.py` | SQLite outbox with claim tokens and item history; stdout, webhook, SMTP, Telegram, Slack, Discord, Matrix and Mastodon channels |
| `explain.py` / `diagnostics.py` / `evaluation.py` | Explaining results, strategy diagnostics, corpus scoring |
| `jsrender.py` | Optional Playwright rendering |
| `async_fetch.py` | Optional aiohttp transport for `batch --async`, under the same fetch policy and cache |
| `model.py` | `Feed` / `Item` typed shapes shared by every strategy and output |
| `settings.py` / `settings_doc.py` | Layered settings: defaults < YAML < environment < CLI; one-line docs that generate the settings reference |
| `language.py` | Evidence-based language support matrix (`newsworker languages`) |
| `mcp_server.py` | Model Context Protocol tools |
| `plugins.py` / `bridges.py` | Third-party extractors and host/path YAML overrides |

Strategy order in `FeedService.get_feed()`: native feed (when the response is
RSS/Atom/JSON Feed and no explicit spec is given) → plugin → bridge → cached or
freshly analysed spec (re-analysed once if it matches nothing) → dynamic
extraction → JSON-LD/microdata when no items were found → undated fallback
(opt-in) → browser rendering (opt-in). Links are then sanitised and item identities
assigned from links before formatting.

The internal feed dict is the API contract between extraction and output. Its
shape is declared in `model.py` as `Feed` and `Item` (`TypedDict`s, so plain
dicts still work): `{title, language, link, description, items: [{title,
description, pubdate, unique_id, content_hash, link, extra: {links, images},
…}], provenance}`. `tests/test_model.py` fails when a strategy emits a key the
model does not declare. mypy checks the whole package.

See [how it works](/getting-started/how-it-works) and
[parsing specs](/guides/parsing-specs).

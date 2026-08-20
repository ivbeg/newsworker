---
title: "Architecture"
description: "Module map and data flow from fetch through extraction to output"
---

# Architecture

newsworker is a thin CLI layer (`core.py`) over a service layer (`service.py`)
that orchestrates:

| Module | Role |
|--------|------|
| `cache.py` | SHA-1-keyed file caches for specs and page content |
| `extractor.py` | Dynamic date-driven feed extraction |
| `spec.py` | YAML spec serialization, `SpecAnalyzer`, `SpecExtractor` |
| `finder.py` | Discovers existing feeds via autodiscovery/icons/heuristics |
| `formats.py` | Renders the internal feed dict to json/rss/atom/csv/opml/… |
| `server.py` | Stdlib HTTP server exposing `/feed`, `/health`, `/` |
| `settings.py` | YAML-backed `Settings` dataclass |
| `fetch.py` / `runtime.py` | Shared network policy and request context |
| `delivery.py` | Watch outbox and delivery channels |
| `jsrender.py` | Optional Playwright rendering |
| `undated.py` | Opt-in undated listing fallback |
| `plugins.py` / bridges | Third-party extractors and host/path YAML overrides |

Typical data flow: `get_feed(url)` → ContentCache → fetch → SpecCache →
SpecAnalyzer → SpecExtractor (fallback to dynamic FeedExtractor) →
`format_feed()`.

The internal feed dict is the API contract between extraction and output:
`{title, language, link, description, items: [{title, description, pubdate,
unique_id, link, extra: {links, images}}]}`.

See [how it works](/getting-started/how-it-works) and
[parsing specs](/guides/parsing-specs).

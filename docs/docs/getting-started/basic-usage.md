---
title: "Basic usage"
description: "Library and CLI patterns for extracting, formatting, and caching feeds"
---

# Basic usage

The package installs a single `newsworker` executable. Add `--verbose` / `-v` to
any command for detailed logs. Run `newsworker --version` to print the installed
version.

```text
newsworker [COMMAND] [ARGS] [OPTIONS]

Commands:
  extract    Extract feed records from a web page
  serve      Run a local HTTP server exposing pages as feeds
  scan       Scan a page and find existing feeds
  analyze    Analyze a page and generate a reusable YAML parsing spec
  batch      Extract feeds from many pages concurrently
  watch      Poll a page and emit/deliver only new items
  cache      Inspect and manage the spec and content caches
  spec       Validate a parsing spec without fetching
  parsedate  Parse a date/time string (debugging helper)
```

## High-level Python service

`FeedService` ties together caching, spec building, bridges, plugins, enrichment,
and optional pagination — shared by `extract`, `serve`, `batch`, and `watch`:

```python
from newsworker.service import FeedService
from newsworker.formats import format_feed

service = FeedService()
feed = service.get_feed("https://example.com/news", max_pages=2)
print(format_feed(feed, fmt="rss"))
```

See [Python library](/integrations/python-library) for the lower-level extractor,
spec workflow, and feed finder APIs.

## Caching on first run

By default `extract` builds a parsing spec **dynamically on the first run** for a
URL and caches it, along with the fetched page content, under the configured
cache directory. Subsequent runs reuse the cached spec (deterministic, fast) and
the cached page (until its TTL expires). See [Settings](/guides/settings).

## Fetch defaults

By default newsworker verifies TLS certificates and honors the target site's
`robots.txt`. Use `--insecure` / `--ignore-robots` to override per run. Relative
dates such as "2 hours ago" or "yesterday" are resolved automatically.

## Next steps

- [CLI reference](/commands/)
- [Settings](/guides/settings)
- [Runtime configuration](/guides/runtime-configuration)

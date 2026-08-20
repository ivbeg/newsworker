---
title: "Feed discovery"
description: "Find RSS, Atom, JSON Feed, WebSub, and sitemap-declared feeds"
---

# Feed discovery

Use `scan` when you want feeds the site already publishes rather than
reconstructing items from HTML.

```bash
newsworker scan "https://www.dta.gov.au/news/"
newsworker scan "https://www.dta.gov.au/news/" --format opml --output feeds.opml
newsworker scan "https://example.com" --sitemap --format json
newsworker scan "https://example.com" --no-verify --format csv
```

Verification is enabled by default and fetches bounded candidate bytes through
the shared network policy. `--no-verify` is faster and skips parsing.

JSON/CSV results identify source, declared type, confidence, verification state,
and WebSub metadata. OPML is the usual interchange format for importing into
readers.

See [`scan`](/commands/scan) and [discovery](/guides/discovery).

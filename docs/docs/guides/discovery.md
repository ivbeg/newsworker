---
title: "Feed discovery"
description: "RSS, Atom, JSON Feed, WebSub, and sitemap discovery behaviour"
---

# Modern feed discovery

`newsworker scan` discovers RSS, Atom, and JSON Feed declarations, WebSub
hub/self links, and optionally bounded sitemap URL sets/indexes. Relative URLs
and multi-token `rel` attributes are normalized without losing the declared feed
type or discovery source.

```bash
newsworker scan https://example.com --sitemap --format json
newsworker scan https://example.com --no-verify --format csv
newsworker scan https://example.com --format opml
```

Verification is enabled by default and concurrently fetches bounded candidate
bytes through the shared network policy. Parsers never fetch candidate URLs
themselves. Each JSON/CSV result identifies its source, declared type,
confidence, verification state, and WebSub metadata; OPML/RSS/Atom outputs
retain the normalized candidate URLs.

See [`scan`](/commands/scan).

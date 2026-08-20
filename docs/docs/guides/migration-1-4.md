---
title: "Migration 1.4"
description: "Timezone-aware publication dates, content_kind, and configuration precedence"
---

# Migration notes for the 1.4 contracts

Publication times in the internal feed dictionary are now timezone-aware UTC
`datetime` values. HTML offsets are converted as instants; naive qddate/fuzzy
values use `default_timezone` (UTC by default). Consumers that previously
compared naive values should normalize their own value before comparison:

```python
from newsworker.tools import normalize_datetime

same_instant = item["pubdate"] == normalize_datetime(old_value, "Europe/Paris")
```

Full article content has a `content_kind` of `text` or `html`. JSON Feed selects
`content_text`/`content_html` accordingly, and RSS/Atom use the corresponding
content type. Enclosures are emitted only when both a real byte length and media
type are known; the raw image URL remains in `extra.images` otherwise.

Configuration precedence is now CLI, environment, YAML, then defaults. In
particular, commands no longer replace a configured user agent or filter length
merely because no matching option was supplied.

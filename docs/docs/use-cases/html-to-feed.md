---
title: "HTML to feed"
description: "Extract a structured feed from a news listing that has no RSS/Atom"
---

# HTML to feed

Turn a dated news listing into JSON, RSS, Atom, or another supported format.

```bash
newsworker extract "https://example.com/news" --format rss --output feed.xml
newsworker extract "https://example.com/news" --format jsonfeed
newsworker extract "https://example.com/news" --limit 20 --since 2026-01-01
```

Follow pagination and optionally enrich full article text:

```bash
pip install "newsworker[fulltext]"
newsworker extract "https://example.com/news" --max-pages 3 --full-text --format atom
```

From Python:

```python
from newsworker.service import FeedService
from newsworker.formats import format_feed

feed = FeedService().get_feed("https://example.com/news")
print(format_feed(feed, fmt="rss"))
```

See [`extract`](/commands/extract) and [output formats](/guides/output-formats).
If you will crawl the same layout again, switch to a
[parsing spec](/use-cases/parsing-specs).

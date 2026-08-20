---
title: "Quick Start"
description: "Task-oriented first success paths for newsworker"
---

# Quick Start

Short task-oriented paths to first success. Not sure where to start? Pick your
role and goal in the [cookbook](/getting-started/cookbook).

## HTML page → RSS in 30 seconds

```bash
pip install newsworker
newsworker extract "https://www.eib.org/en/index.htm" --format rss
```

Save it to a file:

```bash
newsworker extract "https://example.com/news" --format rss --output feed.xml
```

## Discover feeds a site already publishes

```bash
newsworker scan "https://www.dta.gov.au/news/" --format opml --output feeds.opml
```

## Analyze once, extract fast

```bash
newsworker analyze "https://example.com/news" -o example.yaml
newsworker extract "https://example.com/news" --spec example.yaml --format rss
```

## Serve a page as a live feed

```bash
newsworker serve --port 8787
```

Then subscribe in a reader:

```text
http://127.0.0.1:8787/feed?url=https%3A%2F%2Fexample.com%2Fnews&format=atom
```

## Use it from Python

```python
from newsworker.service import FeedService
from newsworker.formats import format_feed

service = FeedService()
feed = service.get_feed("https://www.eib.org/en/index.htm")
print(format_feed(feed, fmt="rss"))
```

## Next steps

- [Cookbook](/getting-started/cookbook) — pick a role and a goal
- [How it works](/getting-started/how-it-works)
- [CLI reference](/commands/)
- [Output formats](/guides/output-formats)

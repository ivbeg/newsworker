---
title: "Python library"
description: "FeedService, extractors, specs, and feed discovery from Python"
---

# Python library

## High-level service (recommended)

`FeedService` ties together caching, spec building, bridges, plugins,
enrichment, and optional pagination — shared by `extract`, `serve`, `batch`,
and `watch`:

```python
from newsworker.service import FeedService
from newsworker.formats import format_feed

service = FeedService()
feed = service.get_feed("https://example.com/news", max_pages=2)
print(format_feed(feed, fmt="rss"))
```

## Extract a feed dynamically

```python
from newsworker.extractor import FeedExtractor

extractor = FeedExtractor(filtered_text_length=150)
feed, session = extractor.get_feed(url="https://www.eib.org/en/index.htm")
```

`feed` is a dictionary shaped like:

```python
{
    "title": "European Investment Bank (EIB)",
    "language": "en",
    "link": "https://www.eib.org/en/index.htm",
    "description": "European Investment Bank (EIB)",
    "items": [
        {
            "title": "Blockchain Challenge: coders at the EIB",
            "description": "...",
            "pubdate": datetime.datetime(2018, 6, 18, 0, 0, tzinfo=datetime.timezone.utc),
            "unique_id": "f9d359f76118076c5331ffec3cdb82eb",
            "link": "https://www.youtube.com/watch?v=YlKa2LZgxhE",
            "author": "Jane Doe",
            "categories": ["EU", "Finance"],
            "content": "...full text...",
            "extra": {"links": [...], "images": [...]},
            "raw_html": b"...",
        },
    ],
    "cache": {"pats": ["dt:date:date_1"]},
}
```

## Render a feed in any format

```python
from newsworker.formats import format_feed

print(format_feed(feed, fmt="rss", public_url="https://example.com/feed.xml"))
print(format_feed(feed, fmt="atom"))
print(format_feed(feed, fmt="csv"))
```

## Reuse cached date patterns

```python
pats = feed["cache"]["pats"]
feed, session = extractor.get_feed(
    url="https://www.eib.org/en/index.htm", cached_p=pats
)
```

## Analyze once, extract fast

```python
from newsworker.spec import SpecAnalyzer, SpecExtractor, FeedSpec

spec = SpecAnalyzer(filtered_text_length=150).analyze("https://example.com/news")
spec.save("example.yaml")

spec = FeedSpec.load("example.yaml")
feed = SpecExtractor().extract("https://example.com/news", spec)
```

## Find existing feeds on a page

```python
from newsworker.finder import FeedsFinder
from newsworker.formats import format_scan

finder = FeedsFinder()
finder.find_feeds("https://www.dta.gov.au/news/")
finder.find_feeds("https://www.dta.gov.au/news/", noverify=False)
finder.find_feeds("https://government.bg/bg/prestsentar/novini", extractrss=True)

results = finder.find_feeds("https://www.dta.gov.au/news/", noverify=False)
print(format_scan(results, fmt="opml"))
```

Local archives use `DocumentSource`; see [local input](/guides/local-input).
Timezones and `content_kind` are documented in [migration 1.4](/guides/migration-1-4).

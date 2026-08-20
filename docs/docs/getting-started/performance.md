---
title: "Performance"
description: "How to keep extraction fast: specs, caches, and pattern reuse"
---

# Performance

[qddate](https://github.com/ivbeg/qddate) was built specifically for this
algorithm; pattern matching is already fast. The largest gains come from
avoiding repeated discovery work.

## Prefer specs for repeated crawls

`analyze` once, then `extract --spec`. Deterministic selectors skip the
discovery heuristics. See [parsing specs](/guides/parsing-specs).

## Cache date patterns in the library

Re-parsing the same site is faster if you reuse the date patterns discovered on
the first pass — it narrows matching from ~350 patterns down to the 2–3 that
actually occur:

```python
from newsworker.extractor import FeedExtractor

extractor = FeedExtractor(filtered_text_length=150)
feed, session = extractor.get_feed(url="https://www.eib.org/en/index.htm")
pats = feed["cache"]["pats"]
feed, session = extractor.get_feed(
    url="https://www.eib.org/en/index.htm", cached_p=pats
)
```

## Spec and content caches

The spec cache stores the YAML parsing spec for a URL. The content cache stores
fetched page bytes with a TTL so a polling reader does not re-download on every
request. Inspect them with `newsworker cache stats`. See [Settings](/guides/settings).

## Discovery verification

Feed discovery without verification (`scan --no-verify`, or `noverify=True` in
the library) is fast. Enabling verification parses every candidate and is slower.

## Browser rendering

Playwright rendering is optional and expensive. Keep default concurrency at one
and measure on your own runner; see [browser rendering](/guides/browser-rendering)
and [benchmarks](/development/benchmarks).

## Runtime reuse

A shared `FeedService` with one extraction context per build is substantially
faster than constructing a complete service for every request. See
[benchmarks](/development/benchmarks).

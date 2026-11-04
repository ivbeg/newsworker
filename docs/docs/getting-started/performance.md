---
title: "Performance"
description: "How to keep extraction fast: specs, caches, and pattern reuse"
---

# Performance

[qddate](https://github.com/ivbeg/qddate) was built specifically for this
algorithm. Since qddate 1.1.0 a page of the extraction corpus takes about
1.7 ms on a first visit and 1 ms with a cached spec. Saved news listings of
11–600 KB take 3–25 ms on a first visit and 1.5–20 ms with a cached spec;
`python.org/downloads`, with 274 items, about 60 ms and 35 ms (see
[benchmarks](/development/benchmarks)). The largest remaining gains come from
avoiding repeated discovery work.

## Prefer specs for repeated crawls

`analyze` once, then `extract --spec`. Deterministic selectors skip the
discovery heuristics. See [parsing specs](/guides/parsing-specs).

## Cache date patterns in the library

Re-parsing the same site is faster if you reuse the date patterns discovered on
the first pass — it narrows matching from qddate's 1,812 generated patterns
down to the few that actually occur:

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

The spec cache stores the YAML parsing spec for a URL. With a cached spec a
build skips the analysis, which roughly halves its time. The spec is read on
every build; install PyYAML with libyaml (its wheels include it) so that it
takes 0.3 ms instead of 2.4 ms. The content cache stores fetched page bytes
with a TTL so a polling reader does not re-download on every request. Inspect
them with `newsworker cache stats`. See [Settings](/guides/settings).

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

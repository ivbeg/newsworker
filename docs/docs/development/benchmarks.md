---
title: "Benchmarks"
description: "Offline runtime and browser-rendering benchmark procedures"
---

# Benchmarks

## Request runtime

`benchmarks/runtime_benchmark.py` compares a shared, concurrent-safe service
using one extraction context per build with constructing a complete service for
every build. It uses an offline two-item HTML fixture, eight worker threads, 50
builds per sample, and performs no network or durable-cache I/O.

```bash
python benchmarks/runtime_benchmark.py
```

The result recorded on 2026-08-04 (Python 3.13.7, Apple Silicon) was:

- Shared request contexts: 543.2 builds/second (median of three samples).
- Isolated service per build: 39.1 builds/second.
- Shared/isolated throughput ratio: 13.89x.

Numbers are directional and should be compared on the same host; the regression
signal is the shared/isolated ratio rather than absolute builds per second.

## Extraction

`benchmarks/extraction_benchmark.py` extracts every page of the offline corpus
(`tests/corpus`) through one shared `FeedService`, without network access, in
two modes: a first visit (no caches: analysis, spec extraction and structured
data) and with cached specs (the spec cache filled by a first pass, as `watch`
and the feed server run). `--pages DIR` uses saved `*.html` pages instead, and
`--profile N` prints the N functions with the most cumulative time.

```bash
python benchmarks/extraction_benchmark.py
python benchmarks/extraction_benchmark.py --pages saved-pages --profile 25
```

Results recorded on 2026-11-04 (Python 3.13, Apple Silicon, best of five
passes). The ten pages are saved listings of debian.org, postgresql.org,
kernel.org, python.org, gov.uk, kremlin.ru, interfax.ru, ria.ru,
tagesschau.de and ansa.it (11–594 KB).

| | corpus, first visit | corpus, cached spec | ten listings, first visit | ten listings, cached spec |
| --- | --- | --- | --- | --- |
| qddate 1.0.17 | 15.9 s | 4.7 s | 10.1 s | 3.3 s |
| qddate 1.1.0 | 0.56 s | 0.49 s | 0.24 s | 0.17 s |
| qddate 1.1.0, one parse and session per build | 0.39 s | 0.22 s | 0.16 s | 0.09 s |

Date matching (qddate) now takes about half of a corpus build on a first visit.
The rest is newsworker's own work on the tree: selecting candidate text nodes,
grouping dates into clusters, reading item fields, structured data and
enrichment.

## Browser rendering

```bash
python benchmarks/browser_benchmark.py
```

See [browser rendering](/guides/browser-rendering) for the measured baseline and
concurrency guidance. See [performance](/getting-started/performance) for
day-to-day extraction advice (specs, caches, pattern reuse).

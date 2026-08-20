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

## Browser rendering

```bash
python benchmarks/browser_benchmark.py
```

See [browser rendering](/guides/browser-rendering) for the measured baseline and
concurrency guidance. See [performance](/getting-started/performance) for
day-to-day extraction advice (specs, caches, pattern reuse).

# Change: Refactor the request runtime for safe concurrency

## Why
The threaded server shares one stateful extractor across requests, while batch workers
create excessive independent services. Request-specific date-parser, response metadata,
and debug state need an explicit lifetime before the server can safely serve concurrent
traffic or reuse expensive resources.

## What Changes
- Introduce an explicit per-run `ExtractionContext` for mutable extraction state.
- Reuse only documented thread-safe HTTP pools and immutable date-pattern resources.
- Give concurrent server and batch work isolated contexts.
- Add per-key single-flight coordination for fetch/analyze/cache population.
- Store content and validator metadata as one logical cache generation.
- Preserve the existing public feed dictionary and SHA-1 URL cache keys.

## Impact
- Affected specs: `request-runtime`
- Affected code: `newsworker/extractor.py`, `newsworker/service.py`,
  `newsworker/server.py`, `newsworker/cache.py`, batch/server tests
- Dependencies: direct regression fixes in `tagmapper.py` and `extractor.py` should land
  first; `harden-unified-fetch-policy` may reuse the resulting context boundary


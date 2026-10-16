## Context
`FeedExtractor` currently owns both reusable resources and mutable request state. The
same instance is shared by `ThreadingHTTPServer`, even though batch code documents that
it is not thread-safe. File cache writes are atomic, but cache-miss computation is not
coalesced.

## Goals / Non-Goals
- Goals: isolate request state, preserve concurrency, reuse safe expensive resources,
  and prevent same-key cache stampedes.
- Non-Goals: redesign the extraction heuristics, change cache keys, or replace the
  public feed dictionary in this change.

## Decisions
- Decision: introduce an `ExtractionContext` passed through analysis and extraction.
  It owns debug counters, per-document date-match memoization, response metadata,
  language metadata, clock/timezone inputs, and qddate session state.
- Decision: the server and batch runner create one context per logical feed build.
- Decision: add a keyed single-flight coordinator around fetch/analyze/store, while
  retaining atomic file replacement for durable cache writes.
- Decision: content bytes and validator metadata carry a shared generation identifier.
- Alternatives considered: a global extraction lock is acceptable only as a temporary
  hotfix because it removes the concurrency promised by `ThreadingHTTPServer`.

## Risks / Trade-offs
- Context plumbing touches multiple modules -> migrate one call path at a time and keep
  compatibility wrappers until all internal callers use the context.
- Reusing a qddate parser may still be unsafe -> treat it as request-local unless tests
  or upstream guarantees prove read-only sharing is safe.
- Single-flight locks may grow without bound -> release and remove entries after the
  final waiter exits.

## Migration Plan
1. Add the context and compatibility defaults without changing behavior.
2. Move response/debug/date state into the context.
3. Switch server and batch callers to context-per-run execution.
4. Add single-flight cache population and cache generation metadata.
5. Remove legacy extractor instance fields after a compatibility window.

## Open Questions
- Can compiled qddate patterns be safely shared independently of parser sessions?
- Should HTTP sessions be thread-local or backed by a small bounded pool?


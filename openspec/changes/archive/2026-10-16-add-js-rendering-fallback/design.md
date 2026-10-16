## Context
A browser executes untrusted page code and can issue secondary requests, making it much
more resource- and security-sensitive than normal HTTP fetching.

## Goals / Non-Goals
- Goals: opt-in support for JS listings, dependency isolation, strict resource bounds,
  policy-aware navigation, and clear provenance.
- Non-Goals: bypass anti-bot controls, solve authenticated interactive browsing, or make
  a browser mandatory for ordinary extraction.

## Decisions
- Decision: implement rendering behind the existing extractor plugin interface and a
  separately installed extra.
- Decision: explicit `--render` is supported first; automatic fallback requires zero
  normal items plus diagnostic evidence and remains configurable.
- Decision: create a bounded browser/context pool and block unnecessary resource types
  by default.
- Decision: validate top-level and redirect navigation; subresource policy is best-effort
  and documented because browsers resolve internally.
- Alternatives considered: embedding Playwright in core would increase install size and
  operational complexity for every user.

## Risks / Trade-offs
- Browser SSRF/subresource access -> isolate processes, apply route interception, and
  recommend container/network sandboxing.
- High memory/CPU -> hard concurrency and page lifetime limits.
- Non-deterministic pages -> wait for documented conditions and preserve rendered HTML
  diagnostics without pretending the result is reproducible.

## Migration Plan
Publish the extra and plugin as experimental, support explicit mode, collect fixtures
and telemetry, then consider automatic fallback after confidence thresholds are stable.

## Open Questions
- Should the plugin live in this repository or a separately versioned package?
- Which resource types and wait conditions should be defaults?


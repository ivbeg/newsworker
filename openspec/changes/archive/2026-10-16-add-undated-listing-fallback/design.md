## Context
Dates are newsworker's strongest precision signal. Removing that requirement increases
coverage and false-positive risk, so undated extraction must remain a distinct strategy.

## Goals / Non-Goals
- Goals: extract coherent repeated news cards without dates, expose uncertainty, and
  avoid fabricated timestamps.
- Non-Goals: treat arbitrary repeated links/products/navigation as news or replace dated
  extraction when dates are available.

## Decisions
- Decision: derive candidates from repeated sibling structures with consistent heading,
  link, optional summary/image, and news-semantic signals.
- Decision: require explicit enablement initially and execute only after stronger
  strategies return no acceptable items.
- Decision: use null `pubdate`, stable link/content IDs, strategy provenance, and a
  confidence reason breakdown.
- Decision: calibrate thresholds against labeled positive and negative fixtures.
- Alternatives considered: assigning fetch time as publication time is misleading and
  would break downstream chronological semantics.

## Risks / Trade-offs
- False positives -> opt-in launch, negative corpus, conservative thresholds, and clear
  low-confidence warnings.
- Dedup without dates -> prefer canonical link; fall back to normalized title/content ID.

## Migration Plan
Add diagnostics/corpus support, implement explicit opt-in fallback, evaluate precision,
then consider enabling it by configuration for trusted workloads.

## Open Questions
- What minimum precision on the negative corpus is required before broader enablement?
- Should undated items sort by document order only or carry a separate discovered-at field?


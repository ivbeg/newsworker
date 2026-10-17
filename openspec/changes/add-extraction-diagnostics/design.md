## Context
The analyzer has an internal cluster score but it is not a stable user-facing measure.
Spec parsing accepts unknown versions and many malformed values until extraction.

## Goals / Non-Goals
- Goals: early spec errors, explainability, stable reason codes, calibrated confidence,
  and machine-readable diagnostics.
- Non-Goals: claim probabilistic accuracy without a labeled corpus or guarantee that
  every high-scoring extraction is semantically correct.

## Decisions
- Decision: define diagnostics as a separate object returned alongside or optionally
  embedded in the feed; keep default feed payloads backward compatible.
- Decision: use stable reason codes plus human descriptions, counts, selectors, chosen
  strategy, timing, and warnings.
- Decision: confidence is a documented bounded score derived from measurable signals
  such as repeated-item count, date coherence, link/title completeness, selector
  specificity, and cross-item consistency.
- Decision: schema validation rejects unsupported major versions and reports precise paths.
- Alternatives considered: debug logs alone are not structured, stable, or suitable for
  batch triage.

## Risks / Trade-offs
- Scores can be mistaken for certainty -> include reason breakdowns and label confidence
  as heuristic.
- Diagnostics may expose source data -> omit full extracted text and redact secrets by default.
- Schema evolution -> version the schema and provide migrations or actionable incompatibility errors.

## Migration Plan
Introduce diagnostic models internally, add validation APIs, expose opt-in CLI/JSON
views, calibrate scores on fixtures, then consider server headers and automatic fallback.

## Open Questions
- Should diagnostics use a JSON Schema artifact in addition to Python validation?
- Which score threshold is appropriate for warnings versus fallback activation?


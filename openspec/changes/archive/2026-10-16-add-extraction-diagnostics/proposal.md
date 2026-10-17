# Change: Add spec validation, extraction explanations, and confidence scoring

## Why
An empty or incorrect-looking feed currently provides little actionable information.
Users need to validate specs before use and understand which plugin, bridge, cached spec,
cluster, selector, or fallback produced a result and how confident the extractor is.

## What Changes
- Add a versioned parsing-spec schema and `spec validate` command/API.
- Add machine-readable extraction diagnostics and `--explain` CLI output.
- Score feed/item extraction confidence with reason codes and warnings.
- Explain zero-item, fallback, selector, date, and field-quality outcomes.
- Expose diagnostics in JSON and optional server headers without changing RSS/Atom by default.
- Establish a labeled fixture corpus for score calibration.

## Impact
- Affected specs: `extraction-diagnostics`
- Affected code: `newsworker/spec.py`, `newsworker/extractor.py`,
  `newsworker/service.py`, CLI/server/formats, fixtures/tests/docs
- Dependencies: benefits from `refactor-request-runtime`; quality thresholds must be
  calibrated before driving automatic fallback decisions


# Change: Improve batch manifests and failure reporting

## Why
Batch output files use opaque URL hashes with no manifest, and the command can complete
successfully despite partial failures. Operators need a stable mapping from sources to
artifacts plus machine-readable status, timing, cache, transport, strategy, and error data.

## What Changes
- Write an optional JSON/CSV manifest for every requested URL.
- Record output path, status, timing, transport, cache/revalidation state, strategy,
  item count, confidence/warnings, and typed error information.
- Add configurable exit behavior for any failure versus partial success.
- Preserve input order and deterministic URL-to-output mapping.
- Require threaded and async batch paths to expose equivalent result semantics.

## Impact
- Affected specs: `batch-reporting`
- Affected code: `newsworker/core.py`, `newsworker/service.py`, async transport,
  formats, batch tests/docs
- Dependencies: richer fields integrate with `harden-unified-fetch-policy` and
  `add-extraction-diagnostics`; core manifest/status can land first


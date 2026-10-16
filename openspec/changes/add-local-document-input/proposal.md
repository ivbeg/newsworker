# Change: Add local file and standard-input extraction

## Why
`extract` and `analyze` require a live URL even though their lower layers already accept
pre-fetched bytes. Local files and stdin make extraction reproducible for archived pages,
debugging, tests, and pipelines without weakening network policy.

## What Changes
- Accept a local HTML file or `-` for stdin in `extract` and `analyze`.
- Require or derive an explicit base URL for resolving relative links.
- Keep local input separate from fetchable URL schemes and bypass network/cache reads.
- Record input provenance in diagnostics and generated specs.
- Define mutually exclusive CLI source options and clear errors.

## Impact
- Affected specs: `local-document-input`
- Affected code: `newsworker/core.py`, `newsworker/service.py`, spec/extractor entry points,
  CLI tests/docs
- Dependencies: integrates naturally with `harden-unified-fetch-policy` and
  `add-extraction-diagnostics` but can be implemented independently


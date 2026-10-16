# Change: Expand and measure language support

## Why
The README lists nine date languages, while text-language heuristics recognize additional
scripts and qddate support is an external dependency. A fixture-driven language matrix
is needed before adding high-demand languages or claiming support.

## What Changes
- Define tested levels for date parsing, metadata detection, text detection, and complete extraction.
- Add fixture packs for prioritized languages and scripts.
- Coordinate missing date patterns with qddate rather than duplicating its engine in core.
- Add per-language regression and quality reporting in CI.
- Improve explicit language override/fallback diagnostics.
- Document supported, partial, and unsupported language levels accurately.

## Impact
- Affected specs: `language-support`
- Affected code: date/language helpers, qddate dependency, fixtures/tests/docs,
  diagnostics and release process
- Dependencies: confidence/diagnostic reporting from `add-extraction-diagnostics` is useful
  but not required for the initial matrix


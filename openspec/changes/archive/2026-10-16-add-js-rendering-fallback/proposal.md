# Change: Add an optional JavaScript rendering fallback

## Why
Client-rendered news listings can return little or no usable HTML to the normal fetcher.
The existing plugin seam can support a headless-browser fallback without adding a heavy
mandatory dependency or changing default extraction behavior.

## What Changes
- Add an optional browser extra and extractor plugin, initially using Playwright.
- Support explicit rendering and an optional diagnostic-driven fallback after zero items.
- Apply URL/address policy before navigation and to browser subresources where feasible.
- Enforce navigation, time, memory, response, redirect, and concurrency limits.
- Record rendered provenance, timing, and fallback reasons in diagnostics.
- Fail clearly or fall back normally when the optional dependency/browser is absent.

## Impact
- Affected specs: `js-rendering`
- Affected code: optional dependencies, plugins, CLI/settings, fetch/security boundary,
  diagnostics, fixtures/tests/docs
- Dependencies: `harden-unified-fetch-policy` and `add-extraction-diagnostics` should land first


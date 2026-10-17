# Change: Add modern and bounded feed discovery

## Why
Discovery focuses on RSS/Atom and a single sitemap document, verifies candidates
serially, and loses some candidate type information. Modern sites also advertise JSON
Feed, nested sitemap indexes, and WebSub hubs.

## What Changes
- Discover and verify JSON Feed alongside RSS and Atom.
- Traverse sitemap indexes with depth/count bounds and cycle detection.
- Capture WebSub hub/self relationships when present.
- Preserve candidate type, confidence, source, and verification result during deduplication.
- Verify candidates concurrently with configured bounds and the unified fetch policy.
- Add a fast no-verify CLI mode with explicit unverified status.

## Impact
- Affected specs: `modern-feed-discovery`
- Affected code: `newsworker/finder.py`, discovery formats/CLI, sitemap parsing,
  fixtures/tests/docs
- Dependencies: implement after `harden-unified-fetch-policy`; batch manifest may reuse
  discovery result types


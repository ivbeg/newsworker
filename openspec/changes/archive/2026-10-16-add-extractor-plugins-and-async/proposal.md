# Change: Extractor plugin system, per-site bridges, and async transport

## Why
`newsworker` cannot be extended by third parties and has no per-site override mechanism
(like rss-bridge), nor an async transport for high-throughput batch jobs. These make it a
platform rather than a single tool. (Audit E9, E11, E12.)

## What Changes
- Plugin hook: register custom extractors through the `newsworker.extractors` entry-point
  group so third-party packages can plug in.
- Per-site bridge format: allow sites with known layouts to ship a small Python bridge
  that plugs into `SpecExtractor`, selected by URL/host matching.
- Async transport: an optional `aiohttp`-based fetcher for high-throughput batch jobs,
  with the synchronous path remaining the default.

## Impact
- Affected specs: `feed-extraction`
- Affected code: new plugin registry/loader, `service.py` (extractor selection),
  `spec.py` (bridge integration), optional async fetcher module, `pyproject.toml`
  (entry-point group + optional `aiohttp` extra)

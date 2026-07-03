# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-07-03

### Added
- New `serve` command running a local HTTP feed server (standard-library only,
  no extra dependencies) that turns any page URL into a feed on demand over GET
  (`GET /feed?url=<page>&format=atom`), plus `/health` and `/` endpoints. Feed
  URLs can be pasted straight into any RSS reader.
- New `analyze` command that runs the dynamic heuristics once and distills them
  into a reusable YAML parsing **spec**, and a `--spec` / `-s` option for
  `extract` to run fast, deterministic extraction from a pre-built spec.
- Reusable parsing specs via the new `newsworker.spec` module
  (`FeedSpec`, `SpecAnalyzer`, `SpecExtractor`) — deterministic CSS/XPath
  selectors that avoid re-running the discovery heuristics on known layouts.
- Caching layer (`newsworker.cache`) with a **spec cache** and a **content
  cache** (configurable TTL), so `extract` and `serve` avoid rebuilding specs
  and re-fetching pages. New `--no-cache`, `--refresh` and `--config` / `-c`
  options for `extract`, and `--cache-dir` / `--content-ttl` for `serve`.
- Settings support (`newsworker.settings`) backed by a YAML config file at
  `~/.newsworker/config.yaml` (created with defaults on first run), controlling
  cache directory, TTLs, server host/port and detection parameters.
- High-level `newsworker.service.FeedService` tying together caching, spec
  building and extraction; shared by both the `extract` command and the server.
- Multiple output formats for the `extract` command via `--format` / `-f`:
  `json` (default), `rss`, `atom` and `csv`.
- Multiple output formats for the `scan` command via `--format` / `-f`:
  `json` (default), `rss`, `atom`, `csv` and `opml` (subscription list).
- `--output` / `-o` option for `extract` and `scan` to write results to a file
  instead of stdout.
- New `newsworker.formats` module with `format_feed()` and `format_scan()`
  helpers (RSS/Atom generated via `feedgen`, plus CSV and OPML serializers).

### Changed
- Rewrote `README.md` with a modern structure: table of contents, CLI reference
  tables, output-format and caching documentation, and up-to-date library usage
  examples.
- `extract` now builds and caches a parsing spec on first use (plus the fetched
  page content) so subsequent runs are faster; pass `--spec` to use an explicit
  spec.
- `scan` now emits structured, format-aware output instead of a raw pretty-print.
- Added `cssselect`, `pyyaml`, `requests` and `urllib3` as dependencies (and
  declared `feedparser` explicitly in `setup.py`).
- Moved `PERFORMANCE_ANALYSIS.md` under `docs/` and removed the standalone
  `AUTHORS.md` (authorship is tracked in `setup.py` and the README).

### Fixed
- Naive datetimes are normalized to UTC when rendering RSS/Atom feeds, as
  required by the feed formats.

## [1.0.1] - 2018-07-21

### Added
- First public release on PyPI and github


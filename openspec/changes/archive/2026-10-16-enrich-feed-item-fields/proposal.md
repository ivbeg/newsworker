# Change: Enrich feed items with author, categories, full text; fix enclosure length

## Why
Items currently carry title/description/date/link only. Consumers expect author and
category metadata, and optionally full-article bodies. Also, `formats.py` hardcodes the
enclosure length to `0`. These change the internal feed dict shape, so per the audit they
are batched into one minor release. (Audit A5, A6, A7, A8.)

## What Changes
- **BREAKING (feed dict shape):** add `author` and `categories` to items.
- Extract author from `rel="author"`, `.author`, or `meta[name=author]` within item scope.
- Extract categories/tags from `.tags`, `.categories`, or `rel="tag"` within item scope.
- Fix enclosure length: use a HEAD request for `Content-Length` or omit the attribute
  rather than hardcoding `0`.
- Add a `--full-text` flag that follows each item link and extracts the main body via
  `trafilatura`/`readability-lxml` (optional dependency).
- Propagate the new fields through JSON/RSS/Atom/CSV output.

## Impact
- Affected specs: `feed-extraction`
- Affected code: `spec.py` (FieldRule for author/categories), `extractor.py` (dynamic path),
  `formats.py` (enclosure length + emit author/categories), `core.py` (`--full-text`)
- **BREAKING**: bump the internal API/minor version; downstream consumers gain new keys.

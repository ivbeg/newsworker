# Change: Add JSON Feed, HTML, Markdown and YAML output formats

## Why
`extract` emits only `json` (the raw internal dict), `rss`, `atom`, and `csv`. Modern feed
consumers expect JSON Feed 1.1, and human-facing previews (HTML/Markdown) and YAML are
cheap to add and reuse the existing feed dict without changing its shape. (Audit A1–A4.)

## What Changes
- Add `to_jsonfeed()` producing JSON Feed 1.1 (https://jsonfeed.org/version/1.1).
- Add `to_html()` rendering items as cards (also usable for a server `/preview`).
- Add `to_markdown()` rendering items as a dated bulleted list.
- Add `to_yaml()` via `yaml.safe_dump`, symmetric with the YAML spec format.
- Register the new identifiers in `SUPPORTED_FORMATS` and dispatch in `format_feed()`;
  the CLI inherits them automatically because it validates against `SUPPORTED_FORMATS`.

## Impact
- Affected specs: `output-formats`
- Affected code: `formats.py` (`SUPPORTED_FORMATS`, `format_feed`, new serializers),
  `server.py` (content types for new formats)
- Non-breaking: no change to the internal feed dict shape.

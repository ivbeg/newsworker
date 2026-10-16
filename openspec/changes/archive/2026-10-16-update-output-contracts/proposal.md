# Change: Update feed data and output contracts

## Why
Timezone-bearing HTML dates currently lose their offset and are later labeled UTC,
JSON Feed drops extracted full text, image enclosures can contain fabricated metadata,
and HTML preview attributes are not safe for untrusted source values. These inconsistencies
make outputs disagree about the same extracted item.

## What Changes
- **BREAKING:** normalize publication instants to timezone-aware UTC datetimes in the
  internal feed contract.
- Add an explicit default timezone policy for dates without an offset.
- Define whether full-text content is plain text or HTML and map it consistently to RSS,
  Atom, JSON, JSON Feed, HTML, and YAML.
- Emit image enclosures only with truthful URL, length, and media-type metadata.
- Require safe escaping of all untrusted values in HTML and Markdown-oriented output.
- Add contract tests shared by every renderer.

## Impact
- Affected specs: `output-contracts`
- Affected code: `newsworker/tools.py`, `newsworker/extractor.py`,
  `newsworker/spec.py`, `newsworker/formats.py`, `newsworker/enrich.py`, docs/tests
- Dependencies: effective URL metadata comes from `harden-unified-fetch-policy`
- Release: minor release with migration notes because the internal datetime contract changes


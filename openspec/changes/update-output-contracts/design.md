## Context
qddate produces naive values, HTML `<time>` may include an offset, and renderers apply
their own assumptions. The internal feed dictionary is the package's cross-module API.

## Goals / Non-Goals
- Goals: preserve instants, deterministic naive-date handling, renderer parity, truthful
  enclosure metadata, and safe preview output.
- Non-Goals: replace the public feed dictionary with dataclasses in this change.

## Decisions
- Decision: represent publication instants as aware UTC `datetime` values internally.
- Decision: configure a source/default timezone for naive parsed values; retain UTC as
  the compatibility default and record when it was assumed in diagnostics.
- Decision: store full text with an explicit content kind (`text` or `html`) and map it
  to each format's native field.
- Decision: omit enclosures whose length or media type is unknown rather than inventing
  values; raw image URLs remain available in `extra.images`.
- Decision: renderer contract fixtures contain hostile strings and validate safe output.
- Alternatives considered: preserving original offsets is readable but complicates
  comparisons and deduplication; normalized UTC plus optional source metadata is simpler.

## Risks / Trade-offs
- Consumers comparing naive datetimes may break -> announce the contract change and
  provide a normalization helper/migration example.
- HTML full text may contain unsafe markup -> sanitize before HTML output or emit it as
  escaped text unless explicitly trusted.

## Migration Plan
Add normalization helpers and warnings, update extraction paths, migrate renderers, then
document the aware-UTC contract in the minor release notes.

## Open Questions
- Should original offset/source timezone be retained as optional item metadata?
- Which HTML sanitizer, if any, is acceptable without adding a heavy default dependency?


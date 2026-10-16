## ADDED Requirements

### Requirement: Timezone-aware Publication Instants
The internal feed contract SHALL represent publication instants as timezone-aware UTC
datetimes.

#### Scenario: HTML datetime contains an offset
- **WHEN** an item contains `2026-08-04T12:00:00+05:00`
- **THEN** its internal publication instant SHALL equal `2026-08-04T07:00:00+00:00`

#### Scenario: Parsed date has no timezone
- **WHEN** a date parser returns a naive datetime
- **THEN** the configured default timezone SHALL be applied before normalization and the assumption SHALL be available to diagnostics

### Requirement: Cross-format Full-content Parity
Every format capable of representing full article content SHALL emit the same extracted
content with its declared text or HTML kind.

#### Scenario: JSON Feed with plain full text
- **WHEN** an item has plain full article content
- **THEN** JSON Feed SHALL emit that value as `content_text` rather than replacing it with the summary

#### Scenario: Full content unavailable
- **WHEN** enrichment produces no full article content
- **THEN** renderers SHALL continue to use the existing description/summary behavior

### Requirement: Truthful Enclosure Metadata
The system SHALL NOT fabricate enclosure length or media type values.

#### Scenario: Complete image metadata
- **WHEN** an image URL has a known byte length and media type
- **THEN** formats supporting enclosures SHALL emit those values

#### Scenario: Unknown image metadata
- **WHEN** enclosure length or media type is unknown
- **THEN** the renderer SHALL omit the enclosure while preserving the image URL in non-enclosure metadata

### Requirement: Safe Preview Rendering
HTML and Markdown preview renderers SHALL encode untrusted extracted values for their
output context.

#### Scenario: Link contains an attribute delimiter
- **WHEN** an extracted URL contains quotes or other HTML attribute delimiters
- **THEN** the HTML output SHALL represent the URL as data and SHALL NOT create an additional attribute or scriptable handler

#### Scenario: Title contains Markdown control characters
- **WHEN** an extracted title contains link or emphasis delimiters
- **THEN** Markdown output SHALL preserve the title text without creating unintended markup or links


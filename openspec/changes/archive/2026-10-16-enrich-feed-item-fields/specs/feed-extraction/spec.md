## ADDED Requirements

### Requirement: Per-item Author Extraction
The system SHALL extract a per-item author when present and expose it on the feed item and
in the rendered output formats.

#### Scenario: Author from rel=author
- **WHEN** an item contains an element with `rel="author"`
- **THEN** the item's `author` field is populated with that value

#### Scenario: No author present
- **WHEN** an item has no discoverable author
- **THEN** the item's `author` field is absent or null and output remains valid

### Requirement: Per-item Category Extraction
The system SHALL extract per-item categories/tags when present and expose them as a list
on the feed item and in the rendered output formats.

#### Scenario: Categories from tag markup
- **WHEN** an item contains `.tags`, `.categories`, or `rel="tag"` markup
- **THEN** the item's `categories` field is a list of the detected tags

### Requirement: Correct Enclosure Length
The system SHALL NOT emit a hardcoded enclosure length of zero; it SHALL provide the real
`Content-Length` when known or omit the length attribute.

#### Scenario: Unknown enclosure length
- **WHEN** the enclosure length cannot be determined cheaply
- **THEN** the length attribute is omitted rather than reported as zero

### Requirement: Full-article Body Extraction
The system SHALL optionally follow each item link and extract the main article body when
the user requests full text.

#### Scenario: Extracting full text
- **WHEN** a user runs extraction with `--full-text`
- **THEN** each item's body is populated from the linked article's main content

#### Scenario: Full-text dependency absent
- **WHEN** `--full-text` is requested but the extraction dependency is not installed
- **THEN** the command reports a clear error and does not crash

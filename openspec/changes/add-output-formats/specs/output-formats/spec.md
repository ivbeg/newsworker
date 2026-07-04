## ADDED Requirements

### Requirement: JSON Feed 1.1 Output
The system SHALL render an extracted feed as a JSON Feed 1.1 document selectable via the
`jsonfeed` format identifier.

#### Scenario: Rendering JSON Feed
- **WHEN** a user requests the `jsonfeed` format for a page
- **THEN** the output is a JSON document with `version` set to `https://jsonfeed.org/version/1.1`, a `title`, and an `items` array

#### Scenario: Item field mapping
- **WHEN** an item has a title, link, description and publication date
- **THEN** the JSON Feed item includes `id`, `title`, `url`, `content_text`, and `date_published` (ISO 8601)

### Requirement: HTML Preview Output
The system SHALL render an extracted feed as an HTML document selectable via the `html`
format identifier, with items shown as cards and all text safely escaped.

#### Scenario: Rendering HTML preview
- **WHEN** a user requests the `html` format
- **THEN** a valid HTML document is returned with one card per item showing title, date and link

### Requirement: Markdown Output
The system SHALL render an extracted feed as Markdown selectable via the `markdown`
format identifier.

#### Scenario: Rendering Markdown
- **WHEN** a user requests the `markdown` format
- **THEN** items are emitted as a bulleted list including date, title and link

### Requirement: YAML Output
The system SHALL render an extracted feed as YAML selectable via the `yaml` format
identifier.

#### Scenario: Rendering YAML
- **WHEN** a user requests the `yaml` format
- **THEN** the feed dictionary is emitted as valid YAML

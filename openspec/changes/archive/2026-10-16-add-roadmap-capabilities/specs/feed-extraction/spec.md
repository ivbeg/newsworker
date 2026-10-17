## ADDED Requirements
### Requirement: Native Feed Passthrough
When a source URL already serves an RSS, Atom, RDF or JSON Feed document, the system
SHALL map its entries onto the internal item contract instead of running HTML
extraction, keeping publisher entry ids, dates, authors, categories and content.

#### Scenario: Source is an Atom feed
- **WHEN** `extract` is given a URL whose response body is an Atom feed
- **THEN** the items SHALL come from the feed entries with their published dates and authors
- **AND** each item identity SHALL derive from the entry id when one is present

#### Scenario: Native feeds disabled
- **WHEN** `native_feeds` is set to false
- **THEN** feed documents SHALL be processed by the HTML strategies like any other page

### Requirement: Structured-data Article Lists
The system SHALL read JSON-LD (`ItemList`, `@graph`, article types) and microdata
article lists when date-driven extraction finds no items, and SHALL use structured
dates to fill missing publication dates of extracted items.

#### Scenario: Listing with JSON-LD only
- **WHEN** a page has no recognisable date clusters but publishes a JSON-LD `ItemList` of articles
- **THEN** the feed SHALL contain those articles and diagnostics SHALL name the structured-data strategy

#### Scenario: Structured data disabled
- **WHEN** `structured_data` is set to false
- **THEN** JSON-LD and microdata SHALL be ignored

### Requirement: Plausible Publication Dates
Matched dates SHALL be converted to timezone-aware instants and rejected when they
fall before 1970 or more than one year after the extraction time. Two-digit years
SHALL be expanded relative to the extraction time.

#### Scenario: Version number looks like a date
- **WHEN** a text node such as `1.2.3456` matches a date pattern with year 3456
- **THEN** the match SHALL NOT be used as a publication date

### Requirement: Multilingual Relative Dates
Relative publication dates ("2 hours ago", "вчера", "vor 3 Tagen") SHALL be resolved
against the extraction time in English, Russian, Ukrainian, German, French, Spanish,
Italian and Portuguese.

#### Scenario: Russian relative date
- **WHEN** an item shows `3 часа назад` and the extraction time is 12:00 UTC
- **THEN** the item publication date SHALL be 09:00 UTC on the same day

### Requirement: Empty-result Exit Code
`extract` and `scan` SHALL accept `--fail-on-empty` and exit with code 3 when a
source yields no items, so schedulers can detect broken sources.

#### Scenario: Page layout changed
- **WHEN** `newsworker extract URL --fail-on-empty` extracts zero items
- **THEN** the command SHALL exit with code 3

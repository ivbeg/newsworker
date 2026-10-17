## ADDED Requirements

### Requirement: Fuzzy Relative Date Parsing
The system SHALL resolve common relative date expressions into absolute datetimes before
delegating to the underlying date parser.

#### Scenario: Resolving "hours ago"
- **WHEN** an item's date text is "2 hours ago" and the reference time is known
- **THEN** the item's `pubdate` is set to two hours before the reference time

#### Scenario: Resolving named relative days
- **WHEN** an item's date text is "yesterday"
- **THEN** the item's `pubdate` resolves to the calendar day before the reference date

### Requirement: Feed Language Detection
The system SHALL detect the feed language from the page rather than always assuming
English, and SHALL allow an explicit override.

#### Scenario: Detecting from the HTML lang attribute
- **WHEN** a page declares `<html lang="fr">`
- **THEN** the produced feed's `language` is `fr`

#### Scenario: Explicit language override
- **WHEN** a user passes `--language de`
- **THEN** the produced feed's `language` is `de` regardless of detection

#### Scenario: Default when undetectable
- **WHEN** no language can be detected and none is supplied
- **THEN** the feed language defaults to `en`

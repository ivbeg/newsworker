## MODIFIED Requirements

### Requirement: Timezone-aware Publication Instants
The internal feed contract SHALL represent publication instants as timezone-aware UTC
datetimes. A date without a time of day SHALL be represented as 00:00 UTC on the
calendar day it names, without conversion from the default timezone.

#### Scenario: HTML datetime contains an offset
- **WHEN** an item contains `2026-08-04T12:00:00+05:00`
- **THEN** its internal publication instant SHALL equal `2026-08-04T07:00:00+00:00`

#### Scenario: Parsed date has no timezone
- **WHEN** a date parser returns a naive datetime with a time of day
- **THEN** the configured default timezone SHALL be applied before normalization and the assumption SHALL be available to diagnostics

#### Scenario: Date without a time on a site east of UTC
- **WHEN** `default_timezone` is `Europe/Moscow` and an item shows `5 мая 2022`
- **THEN** its publication date SHALL be `2022-05-05T00:00:00+00:00`

## ADDED Requirements

### Requirement: Publication Date Precision
Every item dated by a built-in strategy SHALL carry `date_precision`: `day` when
the source gives no time of day, `minute` or `second` otherwise. Relative dates in
days or longer, and today or yesterday without a clock time, SHALL be `day`.
JSON and YAML SHALL emit the key, CSV SHALL emit a `date_precision` column, JSON
Feed SHALL mark day-precision items with `"_newsworker": {"date_precision": "day"}`,
and HTML and Markdown previews SHALL show a day-precision date without a time.
No output SHALL show a day-precision date on another calendar day than its source.

#### Scenario: RSS output of a calendar day
- **WHEN** an item dated `5 мая 2022` with `default_timezone` `Europe/Moscow` is rendered as RSS
- **THEN** its `pubDate` SHALL be `Thu, 05 May 2022 00:00:00 +0000`

#### Scenario: Structured data adds the time
- **WHEN** a listing shows `5 мая 2022` and the page's JSON-LD gives `2022-05-05T10:15:00+03:00` for the same link
- **THEN** the item SHALL be dated `2022-05-05T07:15:00+00:00` with precision `second`

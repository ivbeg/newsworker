## ADDED Requirements

### Requirement: Date String Inspection
`newsworker parsedate TEXT` SHALL read the text through the same date path as
extraction (page language first, dateline and day-span rewrites, relative
dates, day/month order, offsets, precision and plausibility) and SHALL report
the pattern key, the pattern language, the parser language, the order, the
precision, the offset applied and the resulting UTC time. It SHALL accept
`--json`, `--now` (the reference time), `--timezone` and `--language`, default
the time zone and language to the settings, and exit with code 1 when the text
is not a date.

#### Scenario: Dateline
- **WHEN** the user runs `newsworker parsedate "GENEVA, 29 July 2022"`
- **THEN** the reported UTC time SHALL be `2022-07-29T00:00:00+00:00`, as in extraction

#### Scenario: US order
- **WHEN** the user runs `newsworker parsedate 05/06/2022 --language en-US --json`
- **THEN** the report SHALL give the order `mdy`, the pattern `dt:date:date_usa` and a UTC time on 6 May 2022

#### Scenario: Relative date with a reference time
- **WHEN** the user runs `newsworker parsedate "3 hours ago" --now 2022-05-06T12:00:00+00:00`
- **THEN** the reported UTC time SHALL be `2022-05-06T09:00:00+00:00`

#### Scenario: Not a date
- **WHEN** the text is not a date
- **THEN** the command SHALL say so and exit with code 1

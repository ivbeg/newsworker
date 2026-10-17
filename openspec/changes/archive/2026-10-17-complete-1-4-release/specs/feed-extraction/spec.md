## ADDED Requirements
### Requirement: Datelines, Weekdays and Day Spans
A short date line (at most 64 characters) that does not match as written SHALL
be matched again with a leading label of up to four words before a comma or a
spaced dash removed, and with a leading day span reduced to its first day.
Longer text SHALL NOT be reshaped.

#### Scenario: Press-release dateline
- **WHEN** an item shows `GENEVA, 29 July 2022`
- **THEN** its publication date SHALL be 29 July 2022

#### Scenario: Event span
- **WHEN** an item shows `Bangkok, 21-22 July 2022`
- **THEN** its publication date SHALL be 21 July 2022

#### Scenario: Date inside a sentence
- **WHEN** a paragraph longer than 64 characters mentions `3 May 2022`
- **THEN** the paragraph SHALL NOT be used as a publication date

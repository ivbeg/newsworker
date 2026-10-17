# undated-extraction Specification

## Purpose
An opt-in, conservative fallback for listings that publish no dates, with an honest item contract and confidence reporting.

## Requirements
### Requirement: Conservative Undated Listing Detection
The system SHALL detect undated news listings only from repeated structures that satisfy
configured structural and semantic quality thresholds.

#### Scenario: Repeated news cards without dates
- **WHEN** sibling cards contain consistent titles and article links and satisfy the quality threshold
- **THEN** the fallback SHALL produce undated items with its signal breakdown

#### Scenario: Repeated navigation links
- **WHEN** a repeated structure is primarily navigation, form controls, products, or generic links
- **THEN** the fallback SHALL reject it as a news listing

### Requirement: Fallback Ordering and Enablement
Undated extraction SHALL be explicitly enabled and SHALL run only after stronger
configured strategies fail to produce an acceptable result.

#### Scenario: Dated extraction succeeds
- **WHEN** plugin, bridge, spec, or dated dynamic extraction returns acceptable items
- **THEN** undated extraction SHALL NOT replace that result

#### Scenario: Undated mode disabled
- **WHEN** stronger strategies return no items and undated mode is disabled
- **THEN** the system SHALL return normal zero-item diagnostics without running the fallback

### Requirement: Honest Undated Item Contract
Undated extraction SHALL emit a null publication date and SHALL NOT synthesize one from
fetch or discovery time.

#### Scenario: Undated item emitted
- **WHEN** the fallback accepts a card
- **THEN** the item SHALL have `pubdate: null`, stable identity, document ordering, and undated provenance

### Requirement: Undated Confidence Reporting
The fallback SHALL report confidence and the signals that caused acceptance or rejection.

#### Scenario: Candidate barely meets threshold
- **WHEN** a listing is accepted near the configured threshold
- **THEN** diagnostics SHALL flag the result for review and expose the contributing signals


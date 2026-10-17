## ADDED Requirements
### Requirement: Enrichment-stable Item Versions
When enrichment is enabled, item history versions SHALL be computed from the item's
values before enrichment (`source_hash`), so values added by enrichers, including
article text that varies between fetches, SHALL NOT create new versions. A history
entry recorded with the previous full-item hash SHALL be treated as the same version
and SHALL NOT be delivered again as an update.

#### Scenario: Enrichment turned on for an existing watch
- **WHEN** `watch --deliver-updates` has recorded items and `enrich: [metadata]` is then enabled
- **THEN** the next poll SHALL NOT deliver any of those items as updated

#### Scenario: Article text varies
- **WHEN** the full text extracted for an unchanged item differs between two polls
- **THEN** the item's version SHALL stay the same

#### Scenario: Publisher edits the title
- **WHEN** a recorded item reappears with a changed title while enrichment is enabled
- **THEN** a new version SHALL be recorded and delivered once with `--deliver-updates`

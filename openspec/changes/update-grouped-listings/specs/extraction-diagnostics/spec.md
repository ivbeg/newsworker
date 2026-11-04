## MODIFIED Requirements
### Requirement: Extraction Explanation Report
`newsworker explain` SHALL report, for a URL or local file, the date clusters found,
the strategy chosen and why, the resulting items and hints when the result looks
wrong, as text, JSON or a self-contained HTML page with a restrictive Content
Security Policy. A listing read from sibling groups SHALL be reported as one date
cluster with the number of groups merged into it.

#### Scenario: Page yields nothing
- **WHEN** `explain` runs on a page where no strategy produced items
- **THEN** the report SHALL list the strategies tried and suggest options such as `--undated` or `--render`

#### Scenario: Grouped listing
- **WHEN** `explain` runs on a page whose listing is split into seven sibling `timeline__group` wrappers
- **THEN** the report SHALL show one chosen date cluster for the wrappers' parent with its date count and `7` groups, and SHALL NOT list the wrappers as separate clusters

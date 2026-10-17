## ADDED Requirements
### Requirement: Extraction Explanation Report
`newsworker explain` SHALL report, for a URL or local file, the date clusters found,
the strategy chosen and why, the resulting items and hints when the result looks
wrong, as text, JSON or a self-contained HTML page with a restrictive Content
Security Policy.

#### Scenario: Page yields nothing
- **WHEN** `explain` runs on a page where no strategy produced items
- **THEN** the report SHALL list the strategies tried and suggest options such as `--undated` or `--render`

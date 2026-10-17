## ADDED Requirements
### Requirement: Generated Settings Reference
Every setting SHALL have a one-line description in code, and the settings
reference page SHALL be generated from it with each default and environment
variable; a test SHALL fail when a setting is undocumented or the page is stale.

#### Scenario: New setting without a description
- **WHEN** a setting is added to the settings class without a description
- **THEN** the test suite SHALL fail

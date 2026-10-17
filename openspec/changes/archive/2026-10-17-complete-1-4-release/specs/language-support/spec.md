## ADDED Requirements
### Requirement: Generated Language Documentation
The language table in the documentation SHALL be generated from the support
matrix in code, and a test SHALL fail when they differ.

#### Scenario: Support level changes
- **WHEN** a language's support level changes in code without updating the docs
- **THEN** the test suite SHALL fail

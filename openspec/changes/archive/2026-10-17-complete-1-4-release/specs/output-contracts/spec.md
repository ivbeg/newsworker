## ADDED Requirements
### Requirement: Typed Feed Contract
The feed and item shapes SHALL be declared as typed dictionaries, and a test
SHALL fail when an extraction strategy emits a key the declaration does not
contain.

#### Scenario: Strategy adds an undeclared key
- **WHEN** a strategy adds a new item key without declaring it
- **THEN** the contract test SHALL fail

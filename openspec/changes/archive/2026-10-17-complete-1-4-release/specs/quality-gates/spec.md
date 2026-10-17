## ADDED Requirements
### Requirement: Locked Dependency Job
CI SHALL install a committed lock file of all runtime and test dependencies on
the oldest and newest supported Python, run the tests on it, and fail when the
lock no longer satisfies the declared dependencies.

#### Scenario: Upstream release breaks the latest matrix
- **WHEN** a new dependency release breaks the default test matrix
- **THEN** the locked job SHALL still show whether the code works with the pinned set

### Requirement: Security and Complexity Lint Rules
Linting SHALL enforce bandit security rules and a cyclomatic complexity limit of
15; functions above the limit when the rule was introduced SHALL be marked
individually and new code SHALL NOT exceed it.

#### Scenario: New complex function
- **WHEN** a change adds a function with complexity above 15 without a marker
- **THEN** the lint job SHALL fail

### Requirement: Documentation Checked Against Code
Tests SHALL fail when a command-line option is missing from its command page or
the generated settings reference differs from the settings in code.

#### Scenario: New option without docs
- **WHEN** a command gains an option that its documentation page does not mention
- **THEN** the test suite SHALL fail

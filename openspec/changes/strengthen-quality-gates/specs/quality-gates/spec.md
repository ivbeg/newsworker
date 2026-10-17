## ADDED Requirements

### Requirement: Enforced Formatting and Expanded Linting
CI SHALL reject code that violates the project's formatter or enabled high-signal lint rules.

#### Scenario: Unformatted source change
- **WHEN** a pull request changes a Python file that is not Ruff-formatted
- **THEN** the formatting job SHALL fail and identify the file

#### Scenario: New high-signal lint defect
- **WHEN** changed code violates an enabled bugbear or correctness-oriented rule
- **THEN** the lint job SHALL fail without requiring unrelated legacy cleanup

### Requirement: Package-wide Type-checking Ratchet
The project SHALL type-check public boundaries and SHALL expand checked function bodies
without reducing the existing checked scope.

#### Scenario: Typed contract regression
- **WHEN** an implementation returns a value incompatible with a typed public contract
- **THEN** CI SHALL report the type error

### Requirement: Coverage Quality Gate
CI SHALL enforce an increasing statement/branch coverage floor and minimum coverage for
security, concurrency, delivery, and network modules.

#### Scenario: Coverage falls below the current floor
- **WHEN** a pull request reduces measured coverage below an enforced threshold
- **THEN** the test job SHALL fail with the affected totals

### Requirement: Installable Artifact Verification
CI SHALL verify built artifacts rather than testing only the source checkout.

#### Scenario: Wheel omits package data
- **WHEN** the built wheel does not contain required bridges or metadata
- **THEN** a clean-install smoke test SHALL fail

#### Scenario: Container starts incorrectly
- **WHEN** the Docker image builds but cannot serve its health endpoint
- **THEN** the Docker CI job SHALL fail

### Requirement: Consistent Python Support Policy
Declared package metadata, classifiers, lint/type targets, documentation, and CI SHALL
describe and test one supported Python range.

#### Scenario: Support range drifts
- **WHEN** one maintained configuration advertises a version outside the chosen range
- **THEN** repository validation SHALL report the inconsistency


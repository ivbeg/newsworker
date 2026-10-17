# quality-gates Specification

## Purpose
CI gates that keep the project releasable: formatting, linting, type checks, coverage, artifact verification and the Python support policy.
## Requirements
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

### Requirement: Extraction Corpus Gate
CI SHALL score extraction against a labelled corpus of at least 200 stored pages
(precision, recall, F1, title and date accuracy) at a fixed extraction time, fail on
any regression, and publish the score in the job summary. A scheduled network smoke
job SHALL check that a set of live news pages still extract.

#### Scenario: Change breaks one site
- **WHEN** a change makes any corpus case lose an expected item
- **THEN** the corpus job SHALL fail and name the case

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


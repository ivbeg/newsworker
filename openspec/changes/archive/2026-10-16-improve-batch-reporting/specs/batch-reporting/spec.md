## ADDED Requirements

### Requirement: Per-source Batch Manifest
Batch extraction SHALL be able to emit a machine-readable record for every requested source.

#### Scenario: Successful source
- **WHEN** a source produces an output artifact
- **THEN** its manifest record SHALL contain the source URL, artifact path, success status, item count, and elapsed time

#### Scenario: Failed source
- **WHEN** fetching, analysis, extraction, or rendering fails for one source
- **THEN** its manifest record SHALL contain a typed redacted error while other sources continue according to policy

### Requirement: Deterministic Artifact Mapping
The same normalized source and output format SHALL map to the same artifact name unless
the user explicitly selects a different naming policy.

#### Scenario: Repeated batch run
- **WHEN** the same input list and format are processed again
- **THEN** the manifest SHALL map each source to the same output path

### Requirement: Configurable Batch Exit Policy
The command SHALL expose documented exit behavior for partial and total failure.

#### Scenario: Strict failure mode
- **WHEN** any source fails and strict failure mode is enabled
- **THEN** the command SHALL exit unsuccessfully after completing/reporting the batch

#### Scenario: Partial-success mode
- **WHEN** at least one source succeeds and partial-success mode is enabled
- **THEN** successful artifacts SHALL be retained and the manifest SHALL identify every failure

### Requirement: Transport-equivalent Batch Results
Threaded and async transports SHALL expose equivalent manifest fields and failure semantics.

#### Scenario: Same fixture through both transports
- **WHEN** a controlled batch fixture is processed through threaded and async paths
- **THEN** both manifests SHALL agree on source statuses, cache semantics, strategy, and item counts


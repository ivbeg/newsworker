## ADDED Requirements

### Requirement: Request-scoped Extraction State
The system SHALL isolate mutable extraction, date-parser, language, response-metadata,
and diagnostic state to one logical feed build.

#### Scenario: Concurrent feed builds
- **WHEN** two feed builds execute concurrently with different source metadata
- **THEN** each result and diagnostic record SHALL contain only state from its own build

#### Scenario: Failed extraction cleanup
- **WHEN** a feed build raises during analysis or extraction
- **THEN** its request-scoped parser and diagnostic state SHALL be released without affecting a later build

### Requirement: Safe Shared Resource Reuse
The system SHALL share only resources whose thread-safety is documented or enforced by
the runtime.

#### Scenario: Batch worker reuse
- **WHEN** a batch processes multiple URLs with bounded concurrency
- **THEN** workers SHALL reuse safe pools and immutable resources without sharing mutable extraction state

#### Scenario: Extension preservation
- **WHEN** a service is constructed with explicit plugins or bridges
- **THEN** every server or batch worker SHALL use the same configured extension set

### Requirement: Single-flight Cache Population
The system SHALL coalesce concurrent cache misses for the same URL into one upstream
fetch and one spec-analysis operation.

#### Scenario: Concurrent miss for one URL
- **WHEN** multiple requests miss the same content or spec cache key concurrently
- **THEN** one request SHALL populate the cache and the remaining requests SHALL reuse its result

#### Scenario: Body and metadata consistency
- **WHEN** cached body bytes and HTTP validators are read
- **THEN** they SHALL belong to the same completed cache generation


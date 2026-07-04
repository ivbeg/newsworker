## ADDED Requirements

### Requirement: Third-party Extractor Plugins
The system SHALL discover and use custom extractors registered by third-party packages
through a documented entry-point group.

#### Scenario: Registered plugin selected
- **WHEN** an installed package registers an extractor under the `newsworker.extractors` entry-point group that matches a URL
- **THEN** that extractor is used for the URL in preference to the built-in fallback

#### Scenario: No plugin matches
- **WHEN** no registered plugin matches a URL
- **THEN** the built-in spec/dynamic extraction path is used

### Requirement: Per-site Bridges
The system SHALL support per-site bridge definitions that override extraction for sites
with known layouts.

#### Scenario: Bridge matches a host
- **WHEN** a bridge is defined for a host and a matching URL is extracted
- **THEN** the bridge's field rules are applied via `SpecExtractor`

### Requirement: Optional Async Transport
The system SHALL provide an optional asynchronous fetcher for high-throughput batch jobs
while keeping synchronous fetching as the default.

#### Scenario: Async fetcher enabled
- **WHEN** the async extra is installed and async transport is enabled for a batch job
- **THEN** pages are fetched concurrently using the async transport

#### Scenario: Async dependency absent
- **WHEN** the async extra is not installed
- **THEN** the system uses the synchronous transport without error

# js-rendering Specification

## Purpose
Optional headless-browser rendering for pages that build their listings with JavaScript, isolated and clearly attributed.

## Requirements
### Requirement: Optional Browser Rendering
The system SHALL provide JavaScript rendering only through an optional dependency and
SHALL keep normal installations browser-free.

#### Scenario: Explicit render request
- **WHEN** a user enables rendering and the browser extra is installed
- **THEN** the rendered document SHALL be passed through the normal extraction pipeline

#### Scenario: Browser dependency absent
- **WHEN** rendering is requested without the optional dependency
- **THEN** the operation SHALL fail with installation guidance or use an explicitly configured normal-fetch fallback

### Requirement: Controlled Automatic Fallback
Automatic browser fallback SHALL run only when enabled and supported by extraction
diagnostics.

#### Scenario: Normal extraction succeeds
- **WHEN** normal extraction returns acceptable items
- **THEN** the browser SHALL NOT be started

#### Scenario: Normal extraction has zero items
- **WHEN** normal extraction returns zero items and configured diagnostics indicate a client-rendered page
- **THEN** the system MAY attempt one bounded browser-rendered extraction and SHALL record the decision

### Requirement: Browser Resource Isolation
Browser rendering SHALL enforce configured navigation, duration, concurrency, and
resource limits.

#### Scenario: Render exceeds its deadline
- **WHEN** a page does not reach the configured completion condition before its deadline
- **THEN** the page/context SHALL be terminated and the result SHALL contain a typed timeout diagnostic

#### Scenario: Browser navigation targets a blocked address
- **WHEN** top-level navigation or a redirect violates the network address policy
- **THEN** rendering SHALL stop before extracting the document

### Requirement: Rendered Provenance
Results produced from browser-rendered HTML SHALL identify that source in diagnostics.

#### Scenario: Browser fallback produces items
- **WHEN** rendered extraction succeeds after normal extraction failed
- **THEN** diagnostics SHALL report the browser strategy, timing, and normal-fallback reason


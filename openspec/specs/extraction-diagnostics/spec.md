# extraction-diagnostics Specification

## Purpose
Make extraction results inspectable: validated parsing specs, the chosen strategy, a confidence score and safe diagnostic output.
## Requirements
### Requirement: Versioned Parsing-spec Validation
The system SHALL validate parsing specs against a documented versioned schema before
using them for extraction.

#### Scenario: Valid spec
- **WHEN** a spec satisfies the supported schema and version
- **THEN** validation SHALL succeed without fetching its source URL

#### Scenario: Unsupported spec version
- **WHEN** a spec declares an unsupported major version
- **THEN** validation SHALL fail with the version and migration guidance

#### Scenario: Invalid field rule
- **WHEN** a field rule contains an invalid selector, source, type, or required value
- **THEN** validation SHALL identify the precise configuration path and problem

### Requirement: Explainable Extraction Strategy
The system SHALL provide opt-in diagnostics describing how a feed result was produced.

#### Scenario: Cached spec selected
- **WHEN** extraction uses a cached spec
- **THEN** diagnostics SHALL identify the spec strategy, selector match counts, parsed item count, and warnings

#### Scenario: No items extracted
- **WHEN** every configured strategy produces zero items
- **THEN** diagnostics SHALL report the attempted strategies and stable failure reason codes

### Requirement: Extraction Confidence
The system SHALL compute a bounded heuristic confidence score with a reason breakdown
for extracted feeds and, where useful, individual items.

#### Scenario: High-quality repeated listing
- **WHEN** a listing has coherent dates, specific repeated selectors, and complete titles and links
- **THEN** its score SHALL reflect those positive signals and expose them as reasons

#### Scenario: Low-confidence result
- **WHEN** an extraction has weak selectors, inconsistent dates, or missing core fields
- **THEN** diagnostics SHALL include a low-confidence warning without presenting the score as certainty

### Requirement: Diagnostic Data Safety
Diagnostics SHALL exclude configured secrets and minimize copied source content by default.

#### Scenario: Request uses authorization headers
- **WHEN** extraction diagnostics are displayed or serialized
- **THEN** header credentials, cookies, proxy secrets, and server tokens SHALL be redacted

### Requirement: Extraction Explanation Report
`newsworker explain` SHALL report, for a URL or local file, the date clusters found,
the strategy chosen and why, the resulting items and hints when the result looks
wrong, as text, JSON or a self-contained HTML page with a restrictive Content
Security Policy.

#### Scenario: Page yields nothing
- **WHEN** `explain` runs on a page where no strategy produced items
- **THEN** the report SHALL list the strategies tried and suggest options such as `--undated` or `--render`


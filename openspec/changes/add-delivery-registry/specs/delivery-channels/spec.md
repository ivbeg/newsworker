## ADDED Requirements

### Requirement: Delivery-channel Protocol
The system SHALL provide a common protocol for validating, rendering, sending, and
classifying delivery attempts.

#### Scenario: Registered channel selected
- **WHEN** watch configuration references an installed channel
- **THEN** the registry SHALL validate its configuration and create the channel deterministically

#### Scenario: Referenced channel unavailable
- **WHEN** configuration references a missing optional channel
- **THEN** watch SHALL fail before polling with actionable installation guidance

### Requirement: Destination-scoped Acknowledgment
Delivery state SHALL be tracked independently for each channel and destination.

#### Scenario: One of two channels fails
- **WHEN** email succeeds and Telegram fails for the same item
- **THEN** email SHALL remain acknowledged while only the Telegram delivery remains pending

### Requirement: Centralized Delivery Retry
All channels SHALL use the shared durable retry schedule and SHALL classify results as
successful, retryable, or terminal.

#### Scenario: Provider returns a retryable limit response
- **WHEN** a channel classifies a provider response as retryable
- **THEN** the outbox SHALL schedule the next attempt without acknowledging delivery

#### Scenario: Destination is permanently invalid
- **WHEN** a channel classifies the configuration or destination as terminal
- **THEN** the outbox SHALL stop automatic retry and expose the terminal status

### Requirement: Initial Email and Telegram Channels
The registry SHALL provide configured SMTP email and Telegram Bot API implementations.

#### Scenario: Email delivery succeeds
- **WHEN** SMTP accepts a rendered item message within configured limits
- **THEN** the email destination SHALL be acknowledged for that item

#### Scenario: Telegram delivery succeeds
- **WHEN** the Telegram API accepts a rendered item message
- **THEN** the Telegram destination SHALL be acknowledged for that item

### Requirement: Delivery Secret Safety
Channel credentials SHALL NOT be stored in outbox payloads or exposed in logs,
diagnostics, or status output.

#### Scenario: Channel request fails
- **WHEN** an error includes a URL or header containing a channel credential
- **THEN** the reported error SHALL redact the credential


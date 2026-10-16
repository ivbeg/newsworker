## ADDED Requirements
### Requirement: Chat Delivery Channels
The system SHALL provide Slack and Discord incoming-webhook channels and a Matrix
room channel, enabled by their settings and validated before the first poll.
Messages SHALL be plain text with the item title and link, SHALL NOT trigger
mass mentions, and Matrix sends SHALL use the idempotency key as the transaction
id so a retried send is not posted twice.

#### Scenario: Matrix send retried
- **WHEN** a Matrix send times out and the outbox retries it
- **THEN** the retry SHALL reuse the same transaction id and the room SHALL show the item once

#### Scenario: Title contains @everyone
- **WHEN** an item title contains `@everyone` and is delivered to Discord
- **THEN** the message SHALL be sent with mentions disabled

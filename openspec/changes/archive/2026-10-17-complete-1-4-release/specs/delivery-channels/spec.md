## ADDED Requirements
### Requirement: Mastodon Channel
The system SHALL deliver items as Mastodon statuses through `/api/v1/statuses`
with the configured visibility, sending the outbox idempotency key as
`Idempotency-Key`, defusing `@` mentions in titles, and shortening titles so that
title and link fit 500 characters (links counted as 23).

#### Scenario: Retried post
- **WHEN** a status post times out and the outbox retries it
- **THEN** the retry SHALL carry the same `Idempotency-Key`

#### Scenario: Rejected status
- **WHEN** the instance answers `422`
- **THEN** the delivery SHALL be terminal

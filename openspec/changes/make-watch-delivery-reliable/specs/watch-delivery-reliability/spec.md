## ADDED Requirements

### Requirement: Poll-time Upstream Revalidation
Watch mode SHALL contact the watched source on every configured tick and SHALL use
conditional request validators when available.

#### Scenario: Cached page during a watch tick
- **WHEN** cached content is still within the normal content TTL
- **THEN** watch mode SHALL still revalidate the source before deciding that no new items exist

#### Scenario: Upstream content unchanged
- **WHEN** the source responds that cached content is not modified
- **THEN** the tick SHALL reuse the cached body without treating the poll as a failure

### Requirement: Durable Delivery Acknowledgment
The system SHALL acknowledge an item as delivered only after its configured sink reports
success.

#### Scenario: Webhook delivery fails
- **WHEN** every webhook attempt for a new item fails
- **THEN** the item SHALL remain pending and SHALL be eligible for a later retry

#### Scenario: Webhook delivery succeeds
- **WHEN** a webhook accepts a pending item
- **THEN** the system SHALL atomically mark the item delivered and suppress normal redelivery

### Requirement: Restart-safe Delivery Outbox
Pending delivery state SHALL survive process termination and restart.

#### Scenario: Process exits with pending items
- **WHEN** watch mode starts again for the same feed
- **THEN** due pending items SHALL be retried before newly discovered items are acknowledged

### Requirement: Observable Delivery Status
Watch mode SHALL expose whether a tick discovered, delivered, deferred, or failed items.

#### Scenario: One-shot delivery failure
- **WHEN** `--max-iterations 1` ends with an undelivered item
- **THEN** the command SHALL exit unsuccessfully and report the pending item count

#### Scenario: Invalid polling interval
- **WHEN** a user configures a non-positive interval
- **THEN** the command SHALL reject the configuration before entering the watch loop


# watch-delivery-reliability Specification

## Purpose
Reliable watch delivery: poll-time revalidation, durable acknowledgment, a restart-safe outbox and observable status.
## Requirements
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

### Requirement: Multi-source Watch
`watch` SHALL accept sources from a positional URL, `--urls-file` and `--from-opml`
(optionally the OPML `htmlUrl` pages with `--opml-pages`), poll each source in every
cycle, and report a failing source without stopping the others.

#### Scenario: One source of many is down
- **WHEN** one of three watched sources fails to fetch
- **THEN** the other two SHALL still be polled and delivered
- **AND** the cycle SHALL report the failing source

### Requirement: Item History and Update Notifications
Every item seen by `watch` SHALL be recorded with first-seen and last-seen times,
a content hash and a version that increments when its visible content changes.
With `--deliver-updates`, each new version SHALL be delivered once and marked as an
update. `newsworker history` SHALL export the history as JSON Lines or CSV, and
history older than `history_retention_days` SHALL be pruned.

#### Scenario: Article title corrected
- **WHEN** a delivered item reappears with a changed title and `--deliver-updates` is set
- **THEN** the item SHALL be delivered again once, marked as updated, with version 2

### Requirement: Upgrade-safe Item Identity
When an item's identity changes because ids are now derived from links, the
outbox SHALL treat the item as already handled if its previous id (kept as
`content_hash`) is recorded in the 1.3 `seen` table or in the outbox for the same
channel and destination.

#### Scenario: First poll after upgrading from 1.3
- **WHEN** `watch` polls a page whose items were all seen by 1.3
- **THEN** no item SHALL be delivered again


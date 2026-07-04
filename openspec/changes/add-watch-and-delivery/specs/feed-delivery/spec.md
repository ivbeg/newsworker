## ADDED Requirements

### Requirement: Pagination Following
The system SHALL optionally follow "next"-page links during extraction up to a configured
maximum number of pages.

#### Scenario: Following next links
- **WHEN** a page exposes a "next" link and the user allows up to N pages
- **THEN** items from up to N pages are merged into a single feed

#### Scenario: Respecting the page bound
- **WHEN** more pages exist than `--max-pages`
- **THEN** extraction stops at the configured limit

### Requirement: Cross-run Deduplication
The system SHALL persist the identities of emitted items so a subsequent run emits only
items not previously seen.

#### Scenario: Suppressing already-seen items
- **WHEN** an item with a previously recorded `unique_id` is encountered on a later run
- **THEN** that item is not re-emitted

#### Scenario: Emitting new items
- **WHEN** an item's `unique_id` has not been recorded before
- **THEN** the item is emitted and its identity is recorded

### Requirement: Webhook Delivery
The system SHALL deliver newly discovered items to a configured webhook URL as JSON.

#### Scenario: Posting new items
- **WHEN** new items are found and a webhook URL is configured
- **THEN** the items are POSTed as a JSON payload to that URL

#### Scenario: Delivery retry on failure
- **WHEN** a webhook POST fails transiently
- **THEN** delivery is retried with backoff before giving up

### Requirement: Watch Mode
The system SHALL provide a `watch` command that polls a URL on an interval, emits or
delivers only new items, and exits cleanly on a termination signal.

#### Scenario: Polling on an interval
- **WHEN** a user runs `watch <url> --interval 300`
- **THEN** the URL is re-checked every 300 seconds and only new items are emitted/delivered

#### Scenario: Clean shutdown
- **WHEN** the watch process receives an interrupt or termination signal
- **THEN** it stops the loop and exits without leaving partial state

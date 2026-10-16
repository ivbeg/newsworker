## ADDED Requirements
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

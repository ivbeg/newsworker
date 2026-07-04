## ADDED Requirements

### Requirement: Cache Management Command
The CLI SHALL provide a `cache` subcommand with `clear`, `list`, and `stats` operations
covering the spec and content caches.

#### Scenario: Clearing the cache
- **WHEN** a user runs `newsworker cache clear`
- **THEN** cached spec and content entries are removed and a summary of what was cleared is printed

#### Scenario: Listing cache entries
- **WHEN** a user runs `newsworker cache list`
- **THEN** the cached entries for the spec and content caches are listed

#### Scenario: Reporting cache statistics
- **WHEN** a user runs `newsworker cache stats`
- **THEN** the entry count and total size of each cache are reported

#### Scenario: Scoping to a single cache
- **WHEN** a user runs a `cache` operation with `--specs` or `--content`
- **THEN** only the selected cache is affected

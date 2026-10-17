# cli Specification

## Purpose
Command-line behaviour shared by the extraction commands: item limits, date filters, request options, version and logging flags, and cache management.
## Requirements
### Requirement: Item Count Limiting
The `extract` command SHALL support a `--limit`/`-n` option that caps the number of
emitted items after extraction and filtering.

#### Scenario: Limiting emitted items
- **WHEN** a user runs `extract <url> --limit 5` on a page yielding more than five items
- **THEN** exactly the first five items are rendered in the chosen output format

### Requirement: Date Range Filtering
The `extract` command SHALL support `--since` and `--until` options accepting ISO
`YYYY-MM-DD` dates that filter items by their publication date.

#### Scenario: Filtering by since date
- **WHEN** a user runs `extract <url> --since 2026-01-01`
- **THEN** only items whose `pubdate` is on or after 2026-01-01 are emitted

#### Scenario: Items without a date
- **WHEN** an item has no parseable `pubdate` and a date filter is supplied
- **THEN** that item is excluded from the date-filtered output

### Requirement: Configurable HTTP Request Options
The fetching commands SHALL allow overriding the User-Agent, HTTP proxy, request timeout,
custom headers, and a cookie jar via CLI options and corresponding settings.

#### Scenario: Overriding the User-Agent
- **WHEN** a user runs a fetch command with `--user-agent "MyBot/1.0"`
- **THEN** the outgoing request uses that User-Agent header

#### Scenario: Custom repeatable headers
- **WHEN** a user passes `--header "Accept-Language: fr"` one or more times
- **THEN** each header is included on the outgoing request

#### Scenario: SSRF guard preserved
- **WHEN** any fetch option is supplied
- **THEN** the URL is still validated by the SSRF guard before the request is made

### Requirement: Version and Structured Logging Options
The CLI SHALL provide a `--version` option that prints the package version and a
`--json-logs` option that emits logs as JSON.

#### Scenario: Printing the version
- **WHEN** a user runs `newsworker --version`
- **THEN** the current package version is printed and the process exits successfully

#### Scenario: JSON structured logs
- **WHEN** a user runs a command with `--json-logs`
- **THEN** log records are emitted as JSON objects suitable for log ingestion

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

### Requirement: Language Support Command
`newsworker languages` SHALL print the language support matrix as a text table,
JSON or Markdown.

#### Scenario: Script lists supported languages
- **WHEN** a user runs `newsworker languages --format json`
- **THEN** the output SHALL be one JSON object per language with its date, metadata, text and extraction levels

### Requirement: Single-poll Watch
`watch --once` SHALL poll every source once and exit, and SHALL be rejected when
combined with a different `--max-iterations` value.

#### Scenario: Cron run
- **WHEN** cron runs `newsworker watch --urls-file sources.txt --once`
- **THEN** each source SHALL be polled exactly once before the command exits


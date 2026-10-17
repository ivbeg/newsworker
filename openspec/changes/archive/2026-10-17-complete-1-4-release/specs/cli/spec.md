## ADDED Requirements
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

## ADDED Requirements

### Requirement: Evidence-based Language Support Matrix
The project SHALL classify language support from committed fixtures for date parsing,
metadata detection, text detection, and end-to-end extraction.

#### Scenario: Language labeled supported
- **WHEN** documentation labels a language fully supported
- **THEN** committed fixtures SHALL pass the defined date and end-to-end extraction criteria for that language

#### Scenario: Language has only text detection
- **WHEN** script/text detection exists but date fixtures do not meet support criteria
- **THEN** documentation SHALL label the language partial rather than fully supported

### Requirement: Language Fixture Packs
Each added language SHALL include representative positive, ambiguous, and negative date
examples plus at least one complete listing fixture.

#### Scenario: Adding a date format
- **WHEN** support is added for a new localized date form
- **THEN** its fixture pack SHALL verify the parsed instant and guard against nearby false positives

### Requirement: Upstream Date-pattern Coordination
Missing language-specific date patterns SHALL be implemented through qddate when they
belong to the general date engine.

#### Scenario: Required qddate pattern is unavailable
- **WHEN** a selected fixture requires a pattern absent from the installed qddate version
- **THEN** the change SHALL track the upstream addition and minimum compatible qddate release

### Requirement: Explicit Language Override and Diagnostics
An explicit language override SHALL take precedence, and automatic resolution SHALL
explain ambiguous or fallback results when diagnostics are requested.

#### Scenario: User overrides detected language
- **WHEN** the user supplies a valid language override
- **THEN** the feed SHALL use the normalized override regardless of page metadata guesses

#### Scenario: Automatic detection is ambiguous
- **WHEN** no language receives sufficient evidence
- **THEN** the configured default SHALL be used and diagnostics SHALL report the ambiguity


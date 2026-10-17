# local-document-input Specification

## Purpose
Extracting feeds from local files and standard input with unambiguous source selection and provenance.

## Requirements
### Requirement: Local File Input
The extract and analyze workflows SHALL accept HTML bytes from a local file without
performing a network request.

#### Scenario: Extract archived page
- **WHEN** a user supplies an HTML file and a base URL
- **THEN** extraction SHALL use the file bytes and resolve relative links against the base URL

#### Scenario: Local file cannot be read
- **WHEN** the supplied path is missing, unreadable, or not a regular file
- **THEN** the command SHALL fail before extraction with a source-specific error

### Requirement: Standard-input Source
The extract and analyze workflows SHALL accept `-` as standard-input HTML.

#### Scenario: Pipeline input
- **WHEN** HTML bytes are piped to the command with an explicit base URL
- **THEN** the command SHALL process those bytes without fetching the base URL

#### Scenario: Empty standard input
- **WHEN** stdin contains no document bytes
- **THEN** the command SHALL report an empty-input error rather than a valid empty feed

### Requirement: Unambiguous Source Selection
The CLI SHALL accept exactly one document source for an extraction or analysis operation.

#### Scenario: URL and file both supplied
- **WHEN** a user supplies more than one source kind
- **THEN** the command SHALL reject the invocation and identify the conflicting options

### Requirement: Local Input Provenance
Generated diagnostics and parsing specs SHALL distinguish local input from a live network fetch.

#### Scenario: Spec generated from an archive
- **WHEN** analyze creates a spec from local bytes
- **THEN** the spec SHALL retain the base/source URL and record that analysis used local input


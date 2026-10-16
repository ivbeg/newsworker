## ADDED Requirements

### Requirement: TLS Verification by Default
The system SHALL verify TLS certificates by default when fetching pages, and SHALL only
skip verification when the user explicitly opts out.

#### Scenario: Verified fetch by default
- **WHEN** a page is fetched without any insecure option
- **THEN** the HTTP client verifies the server's TLS certificate

#### Scenario: Explicit opt-out
- **WHEN** a user passes `--insecure` (or sets `verify_tls: false`)
- **THEN** TLS verification is disabled for that run only

### Requirement: robots.txt Compliance
The system SHALL consult the target site's `robots.txt` before fetching and SHALL refuse
to fetch URLs disallowed for its User-Agent, unless the user opts out.

#### Scenario: Disallowed URL is refused
- **WHEN** the site's `robots.txt` disallows the requested path for the configured User-Agent
- **THEN** the fetch is refused with an error and no page content is retrieved

#### Scenario: Robots retrieval failure is lenient
- **WHEN** `robots.txt` cannot be retrieved
- **THEN** the fetch is permitted to proceed

#### Scenario: Opting out of robots checks
- **WHEN** a user passes `--ignore-robots`
- **THEN** the fetch proceeds regardless of `robots.txt`

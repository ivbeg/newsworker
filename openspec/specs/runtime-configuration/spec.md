# runtime-configuration Specification

## Purpose
Layered configuration with deterministic precedence, environment variables, early validation and secret redaction.

## Requirements
### Requirement: Deterministic Configuration Precedence
The system SHALL resolve settings in the order explicit CLI option, environment value,
YAML configuration, and built-in default.

#### Scenario: Configured value without CLI override
- **WHEN** a YAML file sets a custom user agent and the command supplies no user-agent option
- **THEN** the resolved user agent SHALL remain the YAML value

#### Scenario: Explicit CLI override
- **WHEN** the same setting exists in every layer and the user explicitly supplies a CLI value
- **THEN** the CLI value SHALL be used

### Requirement: Environment Configuration
The system SHALL support documented `NEWSWORKER_*` environment variables for runtime
settings.

#### Scenario: Container environment override
- **WHEN** `NEWSWORKER_CONTENT_TTL` contains a valid value and no CLI option overrides it
- **THEN** the resolved content TTL SHALL use the environment value

### Requirement: Early Configuration Validation
The system SHALL reject invalid resolved settings before starting network, server,
batch, or watch work.

#### Scenario: Non-positive watch interval
- **WHEN** the resolved watch interval is zero or negative
- **THEN** the command SHALL fail with a field-specific validation message

#### Scenario: Invalid header definition
- **WHEN** a configured HTTP header has an invalid or empty name
- **THEN** the command SHALL reject it before issuing a request

### Requirement: Secret Redaction
The system SHALL prevent configured secrets from appearing in normal logs and
diagnostics.

#### Scenario: Resolved configuration contains credentials
- **WHEN** proxy credentials, authorization headers, API tokens, or cookie paths are displayed
- **THEN** secret values SHALL be redacted while non-secret configuration remains inspectable


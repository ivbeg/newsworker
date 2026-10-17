## ADDED Requirements

### Requirement: Opt-in Legacy TLS Ciphers
The fetch policy SHALL offer only Python's default TLS cipher suites unless
`legacy_tls_ciphers` is enabled (setting, `NEWSWORKER_LEGACY_TLS_CIPHERS`, or
`--legacy-tls-ciphers` on `analyze` and `extract`). When enabled, the requests
and asynchronous transports SHALL also offer TLS 1.2 suites with static RSA key
exchange, while certificate and host-name verification stay as configured by
`verify_tls`. A TLS handshake failure while the option is disabled SHALL report
an error that names the flag and the setting.

#### Scenario: Server accepts only static-RSA suites
- **WHEN** a server offers only `AES256-GCM-SHA384` over TLS 1.2 and `legacy_tls_ciphers` is false
- **THEN** the fetch SHALL fail with an error suggesting `--legacy-tls-ciphers`

#### Scenario: Option enabled
- **WHEN** the same server is fetched with `legacy_tls_ciphers` enabled
- **THEN** the handshake SHALL succeed and the page SHALL be returned

#### Scenario: Certificates still verified
- **WHEN** `legacy_tls_ciphers` is enabled, `verify_tls` is true and the server certificate is self-signed
- **THEN** the fetch SHALL fail certificate verification

#### Scenario: Default requests unaffected
- **WHEN** a default-policy request follows a legacy request to the same host in one session
- **THEN** it SHALL NOT reuse the legacy connection pool

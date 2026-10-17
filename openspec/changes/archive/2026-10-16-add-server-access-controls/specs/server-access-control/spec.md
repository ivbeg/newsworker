## ADDED Requirements

### Requirement: Optional API Token Authentication
The server SHALL support configured API tokens without adding a mandatory third-party
server dependency.

#### Scenario: Valid token
- **WHEN** a protected request supplies a configured valid token
- **THEN** the server SHALL continue normal request processing

#### Scenario: Missing or invalid token
- **WHEN** a protected request omits a token or supplies an invalid token
- **THEN** the server SHALL reject it without revealing configured token values

### Requirement: Request and Concurrency Limits
The server SHALL bound request rate per identified client and the total number of
concurrent feed builds.

#### Scenario: Client exceeds rate limit
- **WHEN** a client exhausts its configured request budget
- **THEN** the server SHALL return a retryable rate-limit response without starting extraction

#### Scenario: Feed workers are saturated
- **WHEN** the concurrent feed-build limit is reached
- **THEN** additional requests SHALL receive a bounded overload response rather than creating unbounded work

### Requirement: Explicit CORS Policy
The server SHALL omit cross-origin permission headers unless allowed origins are
explicitly configured.

#### Scenario: Allowed browser origin
- **WHEN** a request origin matches the configured CORS allow-list
- **THEN** the response SHALL contain the corresponding CORS permission headers

#### Scenario: Unconfigured origin
- **WHEN** no CORS policy permits the request origin
- **THEN** the response SHALL NOT grant that origin cross-origin access

### Requirement: Operational Health and Request Identity
The server SHALL expose liveness and readiness separately and SHALL attach a request ID
to request logs and error responses.

#### Scenario: Service is ready
- **WHEN** required runtime and cache resources are available
- **THEN** readiness SHALL report success with the running version and non-secret status

#### Scenario: Request fails
- **WHEN** feed generation returns a server error
- **THEN** the client SHALL receive a stable problem response and request ID while internal details remain in server logs


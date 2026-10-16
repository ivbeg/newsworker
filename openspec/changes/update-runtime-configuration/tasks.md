## 1. Layered resolution
- [x] 1.1 Add explicit default, YAML, environment, and CLI configuration layers
- [x] 1.2 Implement deterministic merge precedence without command-specific constants
- [x] 1.3 Add immutable resolved settings or equivalent mutation protection

## 2. Validation and secrets
- [x] 2.1 Validate ports, positive intervals/timeouts, page/worker/cache limits, and timezones
- [x] 2.2 Validate URLs, proxy values, headers, allow-lists, and cookie/file paths
- [x] 2.3 Redact secret-bearing values from logs and resolved-config output

## 3. Caller migration
- [x] 3.1 Migrate extract, analyze, scan, serve, batch, watch, and cache commands
- [x] 3.2 Add Docker/Compose environment examples
- [x] 3.3 Document every environment variable and structured-value syntax

## 4. Verification
- [x] 4.1 Add precedence tests for each layer and command
- [x] 4.2 Add invalid-value and secret-redaction tests
- [x] 4.3 Run the full test, lint, and type-check suite


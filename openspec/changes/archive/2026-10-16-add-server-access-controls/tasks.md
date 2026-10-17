## 1. Authentication
- [x] 1.1 Add secret-aware API token configuration and constant-time validation
- [x] 1.2 Protect feed, metrics, and future management routes according to policy
- [x] 1.3 Add safe unauthorized/forbidden problem responses

## 2. Resource controls
- [x] 2.1 Add per-client token-bucket request limiting
- [x] 2.2 Add a global concurrent feed-build bound and overload response
- [x] 2.3 Export rate-limit and saturation metrics when metrics are enabled

## 3. HTTP operations
- [x] 3.1 Add explicit allowed-origin CORS handling and preflight behavior
- [x] 3.2 Add request IDs to logs and error responses
- [x] 3.3 Add liveness/readiness endpoints with version, cache, and worker status
- [x] 3.4 Warn or reject unsafe routable-bind configurations as approved

## 4. Verification and docs
- [x] 4.1 Test auth success/failure, token redaction, limits, CORS, and readiness
- [x] 4.2 Add concurrent overload tests with deterministic clocks
- [x] 4.3 Update Docker, reverse-proxy, and localhost deployment examples
- [x] 4.4 Run the full test, lint, type-check, and Docker smoke suite


# Change: Add server access controls and operational limits

## Why
The feed server can be published through Docker but has no built-in authentication,
rate limiting, or explicit CORS policy. A richer health/readiness response and request
IDs are also needed to operate it safely outside a single-user localhost environment.

## What Changes
- Add optional API-token authentication with constant-time comparison and secret redaction.
- Add bounded per-client request rate and concurrent-work limits.
- Add an explicit disabled-by-default CORS configuration.
- Add request IDs and structured problem responses.
- Expand liveness/readiness with version, cache, dependency, and worker status.
- Preserve dependency-free default server operation.

## Impact
- Affected specs: `server-access-control`
- Affected code: `newsworker/server.py`, `newsworker/settings.py`, metrics/logging,
  Docker/Compose examples, server tests
- Dependencies: implement after `harden-unified-fetch-policy` and
  `refactor-request-runtime`


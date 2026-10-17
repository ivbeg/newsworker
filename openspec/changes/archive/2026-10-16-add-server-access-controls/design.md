## Context
The stdlib server is intentionally lightweight. Controls must not require a framework or
mandatory metrics dependency and must be safe with threaded request handling.

## Goals / Non-Goals
- Goals: protect non-local service deployments, bound resource use, make failures
  traceable, and retain zero extra mandatory dependencies.
- Non-Goals: implement user accounts, browser sessions, OAuth, or a management UI.

## Decisions
- Decision: support one or more static bearer/API tokens loaded from secret-aware
  configuration; authentication is optional for loopback development but required by
  documented public-deployment profiles.
- Decision: use a bounded in-memory token bucket plus a global concurrent-feed-build
  semaphore; reverse proxies may provide stronger distributed limits.
- Decision: CORS is absent unless explicit allowed origins are configured.
- Decision: `/health/live` checks process liveness and `/health/ready` checks service,
  cache, and runtime readiness without contacting arbitrary upstream sources.
- Alternatives considered: requiring an external reverse proxy leaves unsafe Docker
  defaults; adding a web framework violates the dependency constraint.

## Risks / Trade-offs
- In-memory limits reset and are per-process -> document the scope and support proxy
  rate limiting for multi-instance deployments.
- Token configuration may leak -> integrate runtime secret redaction and never return it.

## Migration Plan
Keep existing `/health` as a compatibility liveness alias, add controls disabled for
loopback defaults, update public deployment docs, and warn when binding a routable host
without authentication/allow-list controls.

## Open Questions
- Should routable binds without authentication fail hard or emit a high-severity warning?
- Is trusted-proxy client-IP parsing in scope for the first release?


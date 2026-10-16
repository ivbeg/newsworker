# Change: Make watch polling and delivery reliable

## Why
`watch` currently reuses fresh content-cache entries instead of contacting upstream on
each requested interval. It also records new items as seen before webhook delivery, so
a failed delivery is silently lost on the next poll and after restart.

## What Changes
- Revalidate the watched source on every tick while retaining conditional HTTP requests.
- Add durable pending/delivered state with acknowledgment after successful delivery.
- Retry pending deliveries across process restarts with bounded backoff.
- Report delivery failure through logs, status, metrics, and one-shot exit codes.
- Validate interval and retention configuration and prune old delivered records.

## Impact
- Affected specs: `watch-delivery-reliability`
- Affected code: `newsworker/core.py`, `newsworker/dedup.py`,
  `newsworker/delivery.py`, `newsworker/service.py`, watch/delivery tests
- Dependencies: can use existing conditional revalidation; should later migrate to
  `harden-unified-fetch-policy`


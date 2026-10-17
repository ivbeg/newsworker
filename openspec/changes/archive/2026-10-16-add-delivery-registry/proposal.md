# Change: Add an extensible delivery-channel registry

## Why
Watch mode supports stdout and one webhook implementation. After durable outbox
semantics exist, a small delivery protocol can add email and Telegram without duplicating
retry, idempotency, status, configuration, and observability logic.

## What Changes
- Define a delivery-channel protocol and registry with explicit capability metadata.
- Adapt stdout and webhook delivery to the protocol.
- Add SMTP email and Telegram Bot API channels as optional/configured implementations.
- Reuse the durable outbox, idempotency, retry/backoff, and status model for every channel.
- Support per-channel templates, destinations, limits, and secret redaction.
- Isolate channel failures so one sink does not corrupt another sink's state.

## Impact
- Affected specs: `delivery-channels`
- Affected code: `newsworker/delivery.py`, watch CLI/settings, plugin loading,
  outbox schema, optional dependencies, tests/docs
- Dependencies: `make-watch-delivery-reliable` and `update-runtime-configuration` must land first


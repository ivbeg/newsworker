## Context
The SQLite dedup store combines discovery and acknowledgment in `filter_new`. This
implements at-most-once behavior even though webhook delivery can fail. Content-cache
freshness is also independent of the polling interval.

## Goals / Non-Goals
- Goals: upstream observation at every tick, durable retry, idempotent acknowledgment,
  restart recovery, and bounded state growth.
- Non-Goals: exactly-once delivery to receivers that provide no idempotency support, or
  adding new delivery channels in this change.

## Decisions
- Decision: replace immediate `seen` insertion with an outbox lifecycle of pending,
  attempted, and delivered records.
- Decision: use item UID plus feed URL as the stable idempotency key and include it in
  delivery payloads/headers.
- Decision: contact upstream each tick using conditional validators where available;
  a 304 is a successful unchanged poll.
- Decision: acknowledge only after the selected sink completes successfully.
- Alternatives considered: deleting failed IDs from the existing table is vulnerable
  to process crashes between insert and delete, so durable pending state is preferred.

## Risks / Trade-offs
- Receivers may process a retry twice -> expose an idempotency key and document
  at-least-once semantics.
- Outbox growth -> prune delivered rows after a configurable retention period while
  retaining pending rows.
- Schema migration -> create the new table transactionally and leave the legacy table
  readable until migration completes.

## Migration Plan
Create the outbox schema alongside `seen`, import legacy rows as delivered, switch watch
to pending/acknowledge calls, then remove legacy-only code in a later release.

## Open Questions
- Should stdout delivery be considered acknowledged after `write` or after an explicit
  durable file sink is introduced?
- What default retention period best balances duplicate suppression and database size?


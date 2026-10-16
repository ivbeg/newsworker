## Context
Channel-specific calls currently live directly in the watch tick. Durable delivery needs
separate acknowledgment per destination, not one global seen flag.

## Goals / Non-Goals
- Goals: common delivery lifecycle, independent destination state, optional channel
  implementations, safe secrets, and clear status.
- Non-Goals: build a general workflow engine or guarantee exactly-once behavior from
  third-party providers.

## Decisions
- Decision: a channel implements validate-config, render, send, classify-result, and
  capability metadata.
- Decision: outbox identity includes feed, item UID, channel, and destination identity.
- Decision: retry scheduling is centralized; channels classify errors as success,
  retryable, or terminal.
- Decision: SMTP uses stdlib where sufficient; Telegram uses the unified HTTP policy.
- Decision: channel secrets are referenced from resolved secret-aware configuration and
  never stored in outbox payloads or logs.
- Alternatives considered: separate retry loops per channel duplicate correctness logic
  and make multi-channel acknowledgment ambiguous.

## Risks / Trade-offs
- Provider-specific semantics -> keep the protocol small and allow typed metadata.
- Duplicate delivery after timeout -> include provider-supported idempotency keys where
  possible and document at-least-once behavior.

## Migration Plan
Adapt stdout/webhook first without changing behavior, switch them to durable per-channel
outbox state, then add email and Telegram behind explicit configuration.

## Open Questions
- Should third-party channels use the existing extractor entry-point group or a new
  `newsworker.delivery` group?
- Which templating features are safe enough without a template-engine dependency?


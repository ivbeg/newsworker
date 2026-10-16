## 1. Channel protocol
- [x] 1.1 Define typed channel, configuration, payload, result, and capability contracts
- [x] 1.2 Add a delivery entry-point registry and deterministic selection
- [x] 1.3 Adapt stdout and webhook sinks to the protocol

## 2. Durable multi-channel state
- [x] 2.1 Scope outbox rows and acknowledgment per channel/destination
- [x] 2.2 Centralize retry scheduling and retryable/terminal error classification
- [x] 2.3 Add secret references and log/status redaction

## 3. Initial channels
- [x] 3.1 Add SMTP email with bounded message size and connection timeout
- [x] 3.2 Add Telegram Bot API delivery through the unified HTTP policy
- [x] 3.3 Add simple safe subject/message templates and destination configuration

## 4. Verification and docs
- [x] 4.1 Test independent success/failure across multiple channels
- [x] 4.2 Test restart recovery, terminal errors, retry, idempotency, and redaction
- [x] 4.3 Document channel configuration and delivery guarantees
- [x] 4.4 Run the full test, lint, and type-check suite


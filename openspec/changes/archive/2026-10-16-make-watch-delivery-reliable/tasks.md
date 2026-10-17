## 1. Poll freshness
- [x] 1.1 Add a revalidation mode that contacts upstream while preserving conditional validators
- [x] 1.2 Make every watch tick use revalidation for the first and paginated pages
- [x] 1.3 Validate positive interval, page bound, and retry settings

## 2. Durable delivery state
- [x] 2.1 Add the outbox schema and legacy `seen` migration
- [x] 2.2 Implement pending, claim, acknowledge, fail, and prune operations transactionally
- [x] 2.3 Include stable idempotency keys in webhook requests
- [x] 2.4 Retry due pending records before adding newly discovered items

## 3. Status and operations
- [x] 3.1 Return a failing one-shot exit status when delivery remains unsuccessful
- [x] 3.2 Add structured logs and counters for discovered, pending, retried, delivered, and failed items
- [x] 3.3 Add configurable delivered-row retention and a pruning command/path

## 4. Verification
- [x] 4.1 Test content changes when cache TTL exceeds the watch interval
- [x] 4.2 Test 2xx, 4xx, 5xx, timeout, retry, crash, and restart behavior
- [x] 4.3 Test that successful items are suppressed while failed items remain pending
- [x] 4.4 Run the full test, lint, and type-check suite


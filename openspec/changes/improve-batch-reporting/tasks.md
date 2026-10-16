## 1. Batch result model
- [x] 1.1 Add a typed per-source batch result with success, partial, and failure states
- [x] 1.2 Record deterministic artifact paths, timing, transport, cache, strategy, and item counts
- [x] 1.3 Attach typed/redacted errors and optional confidence diagnostics

## 2. Manifest and exit behavior
- [x] 2.1 Add JSON and CSV manifest writers
- [x] 2.2 Add CLI options for manifest path and failure policy
- [x] 2.3 Preserve input order while deduplicating execution safely
- [x] 2.4 Return documented exit codes for success, partial failure, and total failure

## 3. Transport parity
- [x] 3.1 Make thread and async paths populate the same result fields
- [x] 3.2 Preserve explicit plugins, bridges, settings, and cache behavior across workers

## 4. Verification and docs
- [x] 4.1 Test mixed success/failure manifests and exit codes
- [x] 4.2 Test deterministic paths, duplicate inputs, order, and redaction
- [x] 4.3 Document automation examples for JSON/CSV manifests
- [x] 4.4 Run the full test, lint, and type-check suite


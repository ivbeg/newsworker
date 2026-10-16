## 1. Spec validation
- [x] 1.1 Define supported spec versions, field constraints, and precise validation errors
- [x] 1.2 Add `newsworker spec validate` and library validation API
- [x] 1.3 Add migration or unsupported-version guidance

## 2. Diagnostic model
- [x] 2.1 Add typed strategy, reason, timing, selector, count, and warning diagnostics
- [x] 2.2 Instrument plugin, bridge, spec, dynamic, and fallback decisions
- [x] 2.3 Explain zero-item and partial-field results without logging source secrets

## 3. Confidence scoring
- [x] 3.1 Build a labeled good/poor extraction fixture corpus
- [x] 3.2 Define feed/item score signals and stable reason codes
- [x] 3.3 Calibrate warning thresholds and document their heuristic nature

## 4. Interfaces
- [x] 4.1 Add `--explain` human and JSON CLI output
- [x] 4.2 Add opt-in diagnostics to raw JSON/batch manifests
- [x] 4.3 Add optional server confidence/warning headers within size limits

## 5. Verification
- [x] 5.1 Test invalid specs, unsupported versions, fallback paths, and secret redaction
- [x] 5.2 Test deterministic scores and reason codes across the corpus
- [x] 5.3 Run the full test, lint, and type-check suite


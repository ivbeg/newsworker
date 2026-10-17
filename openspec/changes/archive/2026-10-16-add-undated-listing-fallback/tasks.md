## 1. Corpus and model
- [x] 1.1 Build labeled undated-news and non-news repeated-layout fixtures
- [x] 1.2 Define candidate structure, semantic signals, thresholds, and reason codes
- [x] 1.3 Define stable IDs and ordering without publication dates

## 2. Extraction strategy
- [x] 2.1 Implement repeated sibling/card detection with title/link requirements
- [x] 2.2 Add guards for navigation, forms, product grids, and generic link collections
- [x] 2.3 Run only after stronger strategies fail and explicit policy enables fallback
- [x] 2.4 Emit null dates, undated provenance, and confidence diagnostics

## 3. Interfaces and formats
- [x] 3.1 Add CLI/config opt-in and quality thresholds
- [x] 3.2 Verify all supported formats handle undated items consistently
- [x] 3.3 Document ordering, dedup, and confidence semantics

## 4. Verification
- [x] 4.1 Measure precision/recall against the labeled corpus
- [x] 4.2 Test fallback ordering and non-activation when dated extraction succeeds
- [x] 4.3 Test stable IDs and repeated runs
- [x] 4.4 Run the full test, lint, and type-check suite


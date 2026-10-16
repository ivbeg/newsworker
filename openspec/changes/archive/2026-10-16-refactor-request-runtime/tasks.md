## 1. Runtime context
- [x] 1.1 Add `ExtractionContext` with request-scoped debug, date, language, and response state
- [x] 1.2 Thread the context through dynamic analysis, spec analysis, and spec extraction
- [x] 1.3 Remove request-state reads and writes from shared extractor instance fields

## 2. Concurrent callers
- [x] 2.1 Give each HTTP request an isolated context and safe service resources
- [x] 2.2 Reuse bounded worker resources in threaded and async batch extraction
- [x] 2.3 Preserve explicitly injected plugins and bridges in every worker

## 3. Cache coordination
- [x] 3.1 Add per-key single-flight fetch/analyze/cache population
- [x] 3.2 Store content and validator metadata as one logical generation
- [x] 3.3 Remove orphan metadata during cache clear and eviction

## 4. Verification
- [x] 4.1 Add barrier-based concurrent server tests with distinct languages and validators
- [x] 4.2 Add same-URL cache-stampede and mixed-URL isolation tests
- [x] 4.3 Benchmark batch/server throughput and record before/after results
- [x] 4.4 Run the full test, lint, and type-check suite


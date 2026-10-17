## 1. Source model
- [x] 1.1 Add a document-source abstraction for URL, file, and stdin bytes
- [x] 1.2 Define required base-URL and provenance behavior
- [x] 1.3 Ensure local sources do not enter URL content caches or network policy

## 2. CLI and library
- [x] 2.1 Add mutually exclusive URL/file/stdin options to `extract`
- [x] 2.2 Add the same source options to `analyze`
- [x] 2.3 Expose the source model through the high-level library API

## 3. Verification and docs
- [x] 3.1 Test file/stdin extraction, spec generation, relative links, encodings, and empty input
- [x] 3.2 Test that local input performs no network request
- [x] 3.3 Add archived-page and pipeline examples to documentation
- [x] 3.4 Run the full test, lint, and type-check suite


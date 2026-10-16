## 1. Publication time contract
- [x] 1.1 Add datetime normalization helpers and configurable default timezone
- [x] 1.2 Preserve and convert offsets from HTML datetime attributes
- [x] 1.3 Normalize qddate and fuzzy dates at the extraction boundary
- [x] 1.4 Document the aware-UTC migration for library consumers

## 2. Content and enclosure contract
- [x] 2.1 Add explicit plain-text/HTML full-content metadata
- [x] 2.2 Map full content consistently in JSON Feed, RSS, Atom, JSON, HTML, and YAML
- [x] 2.3 Capture enclosure media type and length during bounded fetches where available
- [x] 2.4 Omit unsupported enclosures instead of fabricating metadata

## 3. Safe rendering
- [x] 3.1 Escape every untrusted HTML attribute and text context correctly
- [x] 3.2 Define safe Markdown escaping for titles and links
- [x] 3.3 Add CSP and nosniff headers to server-rendered HTML responses

## 4. Verification
- [x] 4.1 Add cross-timezone and naive-time regression tests
- [x] 4.2 Add renderer contract tests for full text and enclosures
- [x] 4.3 Add hostile title, link, description, language, image, and content fixtures
- [x] 4.4 Run the full test, lint, and type-check suite

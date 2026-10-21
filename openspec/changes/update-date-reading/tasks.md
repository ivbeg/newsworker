## 1. Page language first
- [x] 1.1 Per-thread qddate parser per language (`thread_date_parser(language)`), with numeric patterns
- [x] 1.2 `ExtractionContext` keeps the page date language, the parser order and pattern sessions
- [x] 1.3 `FeedExtractor.match_text` tries the page language, then all languages for text with letters
- [x] 1.4 qddate results remembered per build, also across pattern restrictions
- [x] 1.5 Dynamic extraction, spec analysis and spec extraction set the page language
- [x] 1.6 Tests, language-support guide and CHANGELOG

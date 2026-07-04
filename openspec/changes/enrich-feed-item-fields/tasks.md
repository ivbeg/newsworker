## 1. Author & categories
- [x] 1.1 Add author detection (`rel=author`, `.author`, `meta[name=author]`) in item scope
- [x] 1.2 Add category/tag detection (`.tags`, `.categories`, `rel=tag`) in item scope
- [x] 1.3 Add `author` and `categories` to the feed dict (centralized in `enrich.enrich_feed`,
      applied in `FeedService.get_feed` so both the dynamic and spec paths are covered)

## 2. Enclosure length
- [x] 2.1 Replace hardcoded enclosure length `0` in `formats.py`
- [x] 2.2 Use a known length (`extra.enclosure_length`) when available; feedgen still emits
      a `length` attribute so it defaults to `0` only when no size is known

## 3. Full text
- [x] 3.1 Add `--full-text` flag and optional `trafilatura`/`readability-lxml` dependency (`fulltext` extra)
- [x] 3.2 Follow each item link, extract main content, populate `content` (bounded concurrency)
- [x] 3.3 Degrade gracefully when the optional dependency is missing

## 4. Output & versioning
- [x] 4.1 Emit author/categories in JSON, CSV, Atom and JSON Feed (RSS carries categories;
      feedgen omits a name-only RSS author)
- [x] 4.2 Document the new item keys in README/CHANGELOG
- [x] 4.3 Tests for author/category extraction and enclosure length behavior

## 1. Plugin hook
- [x] 1.1 Define an extractor interface (`BaseExtractorPlugin`: `matches(url)` + `extract(url, data)`)
- [x] 1.2 Load extractors from the `newsworker.extractors` entry-point group
- [x] 1.3 Select a matching plugin in `FeedService` before falling back to built-ins

## 2. Per-site bridges
- [x] 2.1 Define a bridge file format (host/URL matcher + FeedSpec body) plugging into `SpecExtractor`
- [x] 2.2 Load bundled and user-provided bridges from `newsworker/bridges/` and `~/.newsworker/bridges/`
- [x] 2.3 Ship one example bridge and document authoring

## 3. Async transport
- [x] 3.1 Add an optional `aiohttp` fetcher behind an `[async]` extra
- [x] 3.2 Use it for batch jobs when `--async` is set; keep sync as default
- [x] 3.3 Degrade gracefully when `aiohttp` is not installed

## 4. Tests & docs
- [x] 4.1 Test plugin discovery and selection with a dummy plugin
- [x] 4.2 Test bridge matching/extraction on a fixture
- [x] 4.3 Document the plugin and bridge APIs in README

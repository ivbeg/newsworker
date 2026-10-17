## 1. Serializers
- [x] 1.1 Implement `to_jsonfeed(feed, public_url=None)` per JSON Feed 1.1
- [x] 1.2 Implement `to_html(feed)` rendering items as cards (escaped)
- [x] 1.3 Implement `to_markdown(feed)` (date, title, link per item)
- [x] 1.4 Implement `to_yaml(feed)` via `yaml.safe_dump`

## 2. Wiring
- [x] 2.1 Add `jsonfeed`, `html`, `markdown`, `yaml` to `SUPPORTED_FORMATS`
- [x] 2.2 Add dispatch branches in `format_feed()`
- [x] 2.3 Add HTTP `Content-Type` entries for new formats in `server.py`

## 3. Tests & docs
- [x] 3.1 Golden-file tests for each new format on a fixture feed
- [x] 3.2 Validate JSON Feed output against the 1.1 field set
- [x] 3.3 Document new formats in README

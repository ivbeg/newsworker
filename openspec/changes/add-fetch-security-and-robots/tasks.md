## 1. TLS verification
- [x] 1.1 Add `verify_tls: bool = True` to `Settings`
- [x] 1.2 Change `FeedExtractor.fetch` to use the setting (default verify=True)
- [x] 1.3 Add `--insecure` flag to fetch commands mapping to `verify_tls=False`
- [x] 1.4 Document the behavior change in README/CHANGELOG

## 2. robots.txt
- [x] 2.1 Add `can_fetch(url, user_agent="newsworker")` in `tools.py` using `RobotFileParser`
- [x] 2.2 Add `respect_robots: bool = True` setting and `--ignore-robots` flag
- [x] 2.3 Consult `can_fetch` in `fetch()`; raise `PermissionError` when disallowed
- [x] 2.4 Cache the parsed robots per host; honor `Crawl-delay` when present
- [x] 2.5 Be lenient (allow) when robots.txt fetch fails

## 3. Tests
- [x] 3.1 Test `can_fetch` allow/deny with a fixture robots.txt
- [x] 3.2 Test that a disallowed URL raises before any content fetch
- [x] 3.3 Test that `--insecure` toggles `verify`

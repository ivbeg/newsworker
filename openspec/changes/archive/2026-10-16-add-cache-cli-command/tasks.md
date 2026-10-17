## 1. Cache helpers
- [x] 1.1 Add `list_entries()` and `stats()` (count, total bytes, oldest/newest) to both caches
- [x] 1.2 Add `clear()` to both caches (remove all entries safely)

## 2. CLI
- [x] 2.1 Add a `cache` Typer sub-app with `clear`, `list`, `stats` commands
- [x] 2.2 Support `--specs`/`--content` scoping (default: both) and `--config`
- [x] 2.3 Human-readable output for `list`/`stats`

## 3. Tests & docs
- [x] 3.1 Unit test stats/list/clear against a temp cache dir
- [x] 3.2 Document the `cache` subcommand in README

# Change: Add a `cache` CLI subcommand

## Why
The spec and content caches under `~/.newsworker/cache` can only be managed by hand
today. A `cache` subcommand gives users a supported way to inspect and clear them.
(Audit B9.)

## What Changes
- Add `newsworker cache clear` to delete cached specs and/or content.
- Add `newsworker cache list` to list cached entries.
- Add `newsworker cache stats` to report entry counts and total size per cache.
- Wrap existing `SpecCache` / `ContentCache` operations; add small helpers as needed.

## Impact
- Affected specs: `cli`
- Affected code: `core.py` (new Typer sub-app), `cache.py` (list/stats/clear helpers)

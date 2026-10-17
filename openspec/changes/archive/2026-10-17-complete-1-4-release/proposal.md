# Change: Record the remaining 1.4 capabilities

## Why
After the roadmap capabilities were recorded (`add-roadmap-capabilities`), the
1.4 work added dateline dates, async transport parity, a browser form on the
feed server, a Mastodon channel, `languages`, `watch --once`, an upgrade-safe
item identity, a typed feed contract, stricter lint and typing gates, a locked
dependency set and documentation generated from the code. The specs should
describe 1.4 as released.

## What Changes
- **feed-extraction**: dateline, weekday and day-span date lines.
- **network-fetch-policy**: the asynchronous transport applies the same policy
  and content cache as the threaded one.
- **feed-server**: browser form on `/`.
- **delivery-channels**: Mastodon channel.
- **watch-delivery-reliability**: upgrades keep pre-1.4 item identities.
- **cli**: `languages` command and `watch --once`.
- **language-support**: matrix printed by the CLI and generated into the docs.
- **quality-gates**: locked dependency job, security and complexity lint rules,
  whole-package typing, documentation checked against the code.
- **output-contracts**: typed feed and item contract.
- **runtime-configuration**: generated settings reference.

## Impact
- Affected specs: the ten listed above.
- Affected code: already implemented in PRs #53–#66. No new code in this change.

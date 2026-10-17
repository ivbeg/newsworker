# Change: Update runtime configuration and validation

## Why
CLI commands currently overwrite configured values such as `user_agent` and
`filtered_text_length` when no corresponding CLI flag is supplied. Containers also lack
a first-class environment configuration layer, and invalid numeric/URL settings are
often accepted until runtime.

## What Changes
- Define precedence as explicit CLI, then `NEWSWORKER_*` environment, then YAML config,
  then dataclass defaults.
- Preserve configured values when an option is not explicitly provided.
- Validate numeric bounds, URLs, header names, host lists, and file paths before work starts.
- Add secret-aware display/debug behavior for proxy credentials, headers, tokens, and cookies.
- Apply the same resolved settings model to every CLI command, server, batch, and watch path.

## Impact
- Affected specs: `runtime-configuration`
- Affected code: `newsworker/settings.py`, `newsworker/core.py`, server/service setup,
  Docker/Compose documentation, CLI/settings tests
- Dependencies: server token variables will be added by `add-server-access-controls`


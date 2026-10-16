## Context
Settings are loaded from one YAML file and then commands mutate them using a mix of
explicit flags and hard-coded constants. Typer defaults do not always reveal whether a
value was supplied by the user.

## Goals / Non-Goals
- Goals: deterministic precedence, one validation path, environment support, and secret
  redaction.
- Non-Goals: introduce a remote configuration service or dynamically reload all settings.

## Decisions
- Decision: build a resolved immutable settings object from distinct default, file,
  environment, and explicit CLI layers.
- Decision: use `NEWSWORKER_` plus uppercase field names; structured values use JSON or
  comma-separated syntax documented per field.
- Decision: validate after merging so errors cite the winning source and field.
- Decision: mark secret-bearing values and redact them from logs/diagnostics.
- Alternatives considered: mutating the dataclass in every command retains the current
  ambiguity and duplication.

## Risks / Trade-offs
- Environment parsing can be ambiguous -> keep structured syntax narrow and fail clearly.
- Existing users may rely on hard-coded CLI replacement -> document corrected precedence
  and provide resolved-config diagnostics.

## Migration Plan
Add the resolver behind existing `Settings.load`, migrate one command at a time, add an
optional resolved-config display, then remove command-specific assignments.

## Open Questions
- Should a future system-wide `/etc/newsworker/config.yaml` layer be included now or
  deferred until there is deployment demand?


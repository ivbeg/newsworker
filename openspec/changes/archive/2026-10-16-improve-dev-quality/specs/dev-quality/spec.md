## ADDED Requirements

### Requirement: Pre-commit Hooks
The project SHALL provide a pre-commit configuration that runs linting and formatting
checks before a commit is created.

#### Scenario: Hook catches style issues
- **WHEN** a developer commits a file with lint or formatting violations after `pre-commit install`
- **THEN** the commit is blocked and the offending files are reported (and auto-fixed where possible)

### Requirement: Static Type Checking
The project SHALL run `mypy` in CI over the type-annotated modules so type regressions
are detected automatically.

#### Scenario: Type checking in CI
- **WHEN** a pull request changes an annotated module in a type-incompatible way
- **THEN** the CI `mypy` job reports the type error

### Requirement: Reproducible Dependency Installation
The project SHALL provide pinned dependency versions enabling a reproducible install
distinct from the loose constraints in `pyproject.toml`.

#### Scenario: Installing pinned dependencies
- **WHEN** a user installs from the pinned requirements/lockfile
- **THEN** the resolved dependency versions are deterministic

### Requirement: Developer Documentation Strategy
The project SHALL document where user and developer documentation live and SHALL NOT
maintain stale Sphinx autodoc stubs.

#### Scenario: Finding developer docs
- **WHEN** a contributor looks for documentation guidance
- **THEN** `docs/README.md` describes the documentation layers (README, OpenSpec, optional MkDocs) and how to bootstrap a modern doc site

#### Scenario: No Sphinx autodoc target
- **WHEN** a developer runs `make help`
- **THEN** no Sphinx/`sphinx-apidoc` documentation target is listed

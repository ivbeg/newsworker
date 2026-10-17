## ADDED Requirements
### Requirement: Tagged Release Workflow
Pushing a `vX.Y.Z` tag SHALL build and check the distributions, fail when the tag
does not match the package version, create a GitHub release with the changelog
section and publish a multi-architecture container image to GHCR. Publishing to
PyPI SHALL run only when trusted publishing is explicitly enabled.

#### Scenario: Tag and version disagree
- **WHEN** tag `v1.4.0` is pushed while the package version is `1.3.2`
- **THEN** the workflow SHALL fail before anything is published

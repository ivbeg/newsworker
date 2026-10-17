# deployment Specification

## Purpose
How newsworker is packaged for running as a service: the container image and the Compose deployment.
## Requirements
### Requirement: Container Image
The project SHALL provide a `Dockerfile` that produces an image running the local feed
server, bound to all interfaces on the configured port so it is reachable from outside
the container.

#### Scenario: Building and running the image
- **WHEN** a user runs `docker build -t newsworker .` and then runs the image
- **THEN** the container starts `newsworker serve` listening on `0.0.0.0:8787`

#### Scenario: Persisting config and cache
- **WHEN** a user runs the image with a volume mounted at the newsworker home directory
- **THEN** the config file and caches persist across container restarts

### Requirement: Compose Deployment
The project SHALL provide a `docker-compose.yml` enabling one-command deployment of the
feed server with a published port and a persistent volume.

#### Scenario: One-command deploy
- **WHEN** a user runs `docker compose up`
- **THEN** the feed server is reachable at the published port and its cache is stored on a persistent volume

### Requirement: Tagged Release Workflow
Pushing a `vX.Y.Z` tag SHALL build and check the distributions, fail when the tag
does not match the package version, create a GitHub release with the changelog
section and publish a multi-architecture container image to GHCR. Publishing to
PyPI SHALL run only when trusted publishing is explicitly enabled.

#### Scenario: Tag and version disagree
- **WHEN** tag `v1.4.0` is pushed while the package version is `1.3.2`
- **THEN** the workflow SHALL fail before anything is published


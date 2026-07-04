# Change: Add Docker and docker-compose support

## Why
There is no container image, so deploying the `serve` feed server requires a manual
Python setup. A slim image plus a compose file enables one-command deployment on a
NAS or VPS, which the README already anticipates. (Audit D3.)

## What Changes
- Add a `Dockerfile` based on `python:3.12-slim` that installs the package and runs
  `newsworker serve` bound to `0.0.0.0` on port 8787.
- Add a `docker-compose.yml` that publishes port 8787 and mounts a host directory to
  `~/.newsworker` for persistent config and cache.
- Document container usage in the README.

## Impact
- Affected specs: `deployment`
- Affected code: new `Dockerfile`, `docker-compose.yml`, `.dockerignore`, README section

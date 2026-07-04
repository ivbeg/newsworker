## 1. Image
- [x] 1.1 Add `Dockerfile` on `python:3.12-slim`, install package, non-root user
- [x] 1.2 Set entrypoint to `newsworker serve --host 0.0.0.0 --port 8787`
- [x] 1.3 Add `.dockerignore` (exclude `.git`, caches, build artifacts)

## 2. Compose
- [x] 2.1 Add `docker-compose.yml` publishing `8787:8787`
- [x] 2.2 Mount a named volume / host path to `/root/.newsworker` (or the non-root home)

## 3. Docs & CI
- [x] 3.1 Document `docker build` / `docker compose up` in README
- [x] 3.2 Add a CI job that builds the image

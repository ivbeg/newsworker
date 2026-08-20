---
title: "Installation"
description: "Install newsworker with pip or from source, including optional extras"
---

# Installation

Requires **Python 3.9+**.

### Using pip

```bash
pip install newsworker
```

### Optional extras

Some features require optional dependencies, installed as extras.

| Extra | Enables |
|-------|---------|
| `fulltext` | Follow item links and extract article bodies (`--full-text`, trafilatura) |
| `async` | High-throughput `batch --async` (aiohttp) |
| `browser` | Playwright Chromium rendering fallback (`--render`) |
| `metrics` | Prometheus `/metrics` on the feed server |
| `dev` | pytest, ruff, mypy, pre-commit, build, twine |

```bash
pip install "newsworker[fulltext]"
pip install "newsworker[async]"
pip install "newsworker[browser]"
pip install "newsworker[metrics]"
pip install "newsworker[dev]"

# Combine extras in one install
pip install "newsworker[fulltext,async]"
```

After installing the `browser` extra, install the Chromium runtime once:

```bash
python -m playwright install chromium
```

### Install from source

```bash
git clone https://github.com/ivbeg/newsworker.git
cd newsworker
pip install -e ".[dev]"
```

### Docker

Run the feed server in a container (binds to `0.0.0.0:8787`):

```bash
docker build -t newsworker .
docker run --rm -p 8787:8787 -v newsworker-home:/home/newsworker/.newsworker newsworker
```

Or with Compose (persists config/cache in a named volume):

```bash
docker compose up
```

See [Docker](/integrations/docker) for security notes on publishing the port.

### Requirements

- Python 3.9 or greater
- An outbound HTTP(S) path to the pages you extract (unless you use [local input](/guides/local-input))

## Next steps

- [Quick start](/getting-started/quick-start)
- [How it works](/getting-started/how-it-works)
- [Cookbook](/getting-started/cookbook)

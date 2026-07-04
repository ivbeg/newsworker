FROM python:3.12-slim AS base

# Avoid interactive prompts and keep the image lean.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package first (leveraging Docker layer caching for deps).
COPY pyproject.toml README.md ./
COPY newsworker ./newsworker
RUN pip install --no-cache-dir .

# Run as a non-root user; its home holds the config and caches.
RUN useradd --create-home --uid 10001 newsworker \
    && mkdir -p /home/newsworker/.newsworker \
    && chown -R newsworker:newsworker /home/newsworker
USER newsworker
ENV HOME=/home/newsworker

EXPOSE 8787

# Bind to all interfaces so the server is reachable from outside the container.
ENTRYPOINT ["newsworker", "serve", "--host", "0.0.0.0", "--port", "8787"]

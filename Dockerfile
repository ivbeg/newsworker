FROM python:3.13-slim

LABEL org.opencontainers.image.title="newsworker" \
      org.opencontainers.image.description="Turn any news page into an RSS/Atom/JSON feed" \
      org.opencontainers.image.source="https://github.com/ivbeg/newsworker" \
      org.opencontainers.image.licenses="MIT"

# Avoid interactive prompts and keep the image lean.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package (with Prometheus metrics for the server).
COPY pyproject.toml README.md LICENSE ./
COPY newsworker ./newsworker
RUN pip install --no-cache-dir ".[metrics]"

# Run as a non-root user; its home holds the config and caches.
RUN useradd --create-home --uid 10001 newsworker \
    && mkdir -p /home/newsworker/.newsworker \
    && chown -R newsworker:newsworker /home/newsworker
USER newsworker
ENV HOME=/home/newsworker

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health/live', timeout=3)"]

# The default command is the feed server on all interfaces; any other
# subcommand works too, e.g. `docker run IMAGE extract https://example.com/news`.
ENTRYPOINT ["newsworker"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8787"]

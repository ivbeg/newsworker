#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Local HTTP server that turns page URLs into RSS/Atom/JSON/CSV feeds.

Built entirely on the Python standard library (``http.server``) so it adds no
dependencies. Generated feed URLs are plain GET requests, so they can be pasted
directly into any RSS reader::

    GET /feed?url=<page>&format=atom

Parsing specs are built dynamically and cached on first request, and page
content is cached for the period configured in the settings (see
:mod:`newsworker.settings`). Add ``&refresh=1`` to bypass the caches for a
single request.
"""

import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .formats import SUPPORTED_FORMATS, format_feed
from .service import FeedService
from .settings import Settings

log = logging.getLogger(__name__)

DEFAULT_FORMAT = "atom"

#: Mapping of feed format to HTTP Content-Type header value.
CONTENT_TYPES = {
    "rss": "application/rss+xml; charset=utf-8",
    "atom": "application/atom+xml; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
}

INDEX_TEXT = """newsworker local feed server

Usage:
  GET /feed?url=<page-url>&format=atom|rss|json|csv   Build a feed from a page
  GET /health                                         Health check

Notes:
  - format defaults to '%s'
  - add &refresh=1 to bypass the content/spec caches for one request

Example:
  /feed?url=https://example.com/news&format=atom
""" % DEFAULT_FORMAT


class FeedRequestHandler(BaseHTTPRequestHandler):
    """Handles GET requests for feeds, health checks and the index page."""

    server_version = "newsworker-feed/1.0"

    # ``service`` is attached to the server instance in :func:`run_server`.
    @property
    def service(self):
        return self.server.feed_service  # type: ignore[attr-defined]

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        log.info("%s - %s", self.address_string(), format % args)

    def _send_text(self, status, text, content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/health":
            self._send_text(200, "ok")
            return
        if path == "/":
            self._send_text(200, INDEX_TEXT)
            return
        if path == "/feed":
            self._handle_feed(parse_qs(parsed.query))
            return
        self._send_text(404, "Not found: %s\n" % parsed.path)

    def _handle_feed(self, params):
        urls = params.get("url") or []
        url = urls[0].strip() if urls else ""
        if not url:
            self._send_text(400, "Missing required 'url' query parameter\n")
            return

        fmt = (params.get("format", [DEFAULT_FORMAT])[0] or DEFAULT_FORMAT).lower()
        if fmt not in SUPPORTED_FORMATS:
            self._send_text(
                400,
                "Unsupported format '%s'. Supported formats: %s\n"
                % (fmt, ", ".join(SUPPORTED_FORMATS)),
            )
            return

        refresh_values = params.get("refresh", ["0"])
        force_refresh = refresh_values[0].lower() in ("1", "true", "yes")

        try:
            feed = self.service.get_feed(url, force_refresh=force_refresh)
            rendered = format_feed(feed, fmt=fmt, public_url=url)
        except Exception as e:  # noqa: BLE001 - surface any extraction failure
            log.error("Failed to build feed for %s: %s", url, e)
            self._send_text(502, "Failed to build feed from %s: %s\n" % (url, e))
            return

        self._send_text(
            200, rendered, content_type=CONTENT_TYPES.get(fmt, "text/plain; charset=utf-8")
        )


def run_server(settings=None):
    """Starts the local feed server and blocks until interrupted."""
    settings = settings or Settings()
    server = ThreadingHTTPServer(
        (settings.host, settings.port), FeedRequestHandler
    )
    server.feed_service = FeedService(settings=settings)  # type: ignore[attr-defined]

    base = "http://%s:%d" % (settings.host, settings.port)
    print("newsworker feed server listening on %s" % base)
    print("Example: %s/feed?url=https://example.com/news&format=atom" % base)
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down feed server.")
    finally:
        server.server_close()

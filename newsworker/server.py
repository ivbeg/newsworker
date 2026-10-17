#!/usr/bin/env python
"""Dependency-free threaded feed server with optional access controls."""

from __future__ import annotations

import hashlib
import hmac
import html
import ipaddress
import json
import logging
import os
import threading
import time
import uuid
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from . import __version__
from .formats import SUPPORTED_FORMATS, content_fingerprint, format_feed, newest_pubdate
from .service import FeedService
from .settings import Settings
from .tools import validate_url

log = logging.getLogger(__name__)

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

    _PROM_AVAILABLE = True
    FEED_REQUESTS = Counter("newsworker_feed_requests_total", "Total /feed requests", ["status"])
    FEED_LATENCY = Histogram("newsworker_feed_seconds", "Time spent building a feed")
    RATE_LIMITED = Counter("newsworker_rate_limited_total", "Rate-limited requests")
    ACTIVE_BUILDS = Gauge("newsworker_active_feed_builds", "Concurrent feed builds")
except Exception:
    _PROM_AVAILABLE = False


DEFAULT_FORMAT = "atom"
CONTENT_TYPES = {
    "rss": "application/rss+xml; charset=utf-8",
    "atom": "application/atom+xml; charset=utf-8",
    "json": "application/json; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "jsonfeed": "application/feed+json; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
    "yaml": "application/yaml; charset=utf-8",
}
INDEX_TEXT = """newsworker local feed server

GET /feed?url=<page-url>&format=<fmt>
GET /health/live
GET /health/ready
"""

#: Formats a feed reader subscribes to, offered first on the home page.
READER_FORMATS = ("rss", "atom", "jsonfeed")

# The home page posts its form back to itself and runs no script.
HOME_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


class _Problem(Exception):
    """An HTTP problem raised while building a feed for a request."""

    def __init__(self, status, title, detail):
        super().__init__(detail)
        self.status = status
        self.title = title
        self.detail = detail


def _home_page(url, fmt, *, allowed, feed=None, public_url=None, error=None):
    """The ``/`` page: paste a news page URL, preview its items, copy the feed link."""
    esc = html.escape
    options = "".join(
        f'<option value="{name}"{" selected" if name == fmt else ""}>{name}</option>'
        for name in READER_FORMATS + tuple(f for f in SUPPORTED_FORMATS if f not in READER_FORMATS)
    )
    parts = [
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>newsworker</title><style>",
        "body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem}",
        "input[type=url]{width:100%;padding:.4rem;box-sizing:border-box}",
        "code{word-break:break-all}li{margin:.4rem 0}small{color:#666}",
        ".error{color:#a00}</style></head><body><h1>newsworker</h1>",
    ]
    if not allowed:
        parts.append(
            "<p>This server is protected. Ask its operator for a feed link, created with "
            "<code>newsworker feed-url URL</code>.</p></body></html>"
        )
        return "".join(parts)
    parts.append(
        '<form method="get" action="/"><p><label for="url">News page URL</label><br>'
        f'<input type="url" id="url" name="url" required value="{esc(url)}" '
        'placeholder="https://example.org/news"></p>'
        f'<p><label>Format <select name="format">{options}</select></label> '
        '<button type="submit">Preview</button></p></form>'
    )
    if error is not None:
        parts.append(f'<p class="error">{esc(error.title)}: {esc(str(error.detail))}</p>')
    if feed is not None:
        parts.append(
            "<h2>Subscribe</h2><p>Add this link to your feed reader:</p>"
            f'<p><a href="{esc(public_url)}"><code>{esc(public_url)}</code></a></p>'
            f"<h2>{esc(str(feed.get('title') or url))}</h2>"
        )
        items = feed.get("items") or []
        if not items:
            parts.append("<p>No news items were found on this page.</p>")
        parts.append("<ol>")
        for item in items:
            title = esc(str(item.get("title") or "(untitled)"))
            link = str(item.get("link") or "")
            if link.startswith(("http://", "https://")):
                title = f'<a href="{esc(link)}" rel="noopener noreferrer">{title}</a>'
            pubdate = item.get("pubdate")
            when = f" <small>{esc(pubdate.date().isoformat())}</small>" if pubdate else ""
            parts.append(f"<li>{title}{when}</li>")
        parts.append("</ol>")
    parts.append("</body></html>")
    return "".join(parts)


class TokenBucketLimiter:
    """Thread-safe per-client token buckets with a bounded idle map."""

    def __init__(self, rate_per_minute=0, burst=20, clock=time.monotonic):
        self.rate = max(0.0, float(rate_per_minute) / 60.0)
        self.burst = max(1.0, float(burst))
        self.clock = clock
        self._lock = threading.Lock()
        self._buckets = {}

    def allow(self, client):
        if self.rate <= 0:
            return True, 0
        now = self.clock()
        with self._lock:
            tokens, updated = self._buckets.get(client, (self.burst, now))
            tokens = min(self.burst, tokens + (now - updated) * self.rate)
            if tokens < 1:
                retry = max(1, int((1 - tokens) / self.rate))
                self._buckets[client] = (tokens, now)
                return False, retry
            self._buckets[client] = (tokens - 1, now)
            if len(self._buckets) > 10000:
                cutoff = now - 3600
                self._buckets = {
                    key: value for key, value in self._buckets.items() if value[1] >= cutoff
                }
        return True, 0


def feed_signature(key, url, fmt):
    """HMAC authorising ``GET /feed`` for exactly this source URL and format."""
    message = f"{fmt}\n{url}".encode()
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()[:32]


def public_feed_url(settings, url, fmt=DEFAULT_FORMAT):
    """The subscription URL for a source page, signed when a key is configured."""
    base = (getattr(settings, "public_base_url", "") or "").rstrip("/")
    if not base:
        host = getattr(settings, "host", "127.0.0.1")
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        base = f"http://{host}:{getattr(settings, 'port', 8787)}"
    query = {"url": url, "format": fmt}
    key = getattr(settings, "feed_signing_key", "")
    if key:
        query["sig"] = feed_signature(key, url, fmt)
    return f"{base}/feed?{urlencode(query)}"


def _feed_request(params):
    """The (source URL, format) a /feed request asks for, as the handler reads them."""
    urls = params.get("url") or []
    url = urls[0].strip() if urls else ""
    fmt = (params.get("format", [DEFAULT_FORMAT])[0] or DEFAULT_FORMAT).lower()
    return url, fmt


def _etag_matches(header, etag):
    """RFC 9110 weak comparison of an ``If-None-Match`` header against ``etag``."""
    if not header:
        return False
    if header.strip() == "*":
        return True
    bare = etag[2:] if etag.startswith("W/") else etag
    for candidate in header.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == bare:
            return True
    return False


class FeedRequestHandler(BaseHTTPRequestHandler):
    server_version = "newsworker-feed/1.4"

    @property
    def service(self):
        return self.server.feed_service  # type: ignore[attr-defined]

    @property
    def settings(self):
        return self.service.settings

    def log_message(self, format, *args):  # noqa: A002
        log.info(
            "%s request_id=%s %s",
            self.address_string(),
            getattr(self, "request_id", "-"),
            format % args,
        )

    def _request_headers(self, content_type):
        headers = {
            "X-Request-ID": self.request_id,
            "X-Content-Type-Options": "nosniff",
        }
        if content_type.startswith("text/html"):
            headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'unsafe-inline'; img-src https: http: data:; "
                "base-uri 'none'; form-action 'none'"
            )
        origin = self.headers.get("Origin")
        allowed = getattr(self.settings, "cors_allowed_origins", []) or []
        if origin and origin in allowed:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Vary"] = "Origin"
        return headers

    def _send_text(
        self, status, text, content_type="text/plain; charset=utf-8", extra_headers=None
    ):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        headers = self._request_headers(content_type)
        headers.update(extra_headers or {})
        for key, value in headers.items():
            self.send_header(key, str(value))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _problem(self, status, title, detail):
        payload = {
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "request_id": self.request_id,
        }
        self._send_text(
            status,
            json.dumps(payload),
            "application/problem+json; charset=utf-8",
        )

    def _send_not_modified(self, etag):
        self.send_response(304)
        self.send_header("ETag", etag)
        for key, value in self._request_headers("text/plain").items():
            self.send_header(key, value)
        self.end_headers()

    def _tokens(self):
        return getattr(self.settings, "api_tokens", []) or []

    def _signing_key(self):
        return getattr(self.settings, "feed_signing_key", "") or ""

    def _signed(self, params):
        """Whether ``params`` carry a valid signature for the feed they request."""
        key = self._signing_key()
        supplied = (params.get("sig") or [""])[0]
        if not key or not supplied:
            return False
        url, fmt = _feed_request(params)
        return hmac.compare_digest(supplied, feed_signature(key, url, fmt))

    def _authorized(self, *, feed=False):
        tokens = self._tokens()
        if not tokens:
            # A signing key alone protects /feed: only signed links pass there.
            return not (feed and self._signing_key())
        supplied = self.headers.get("X-API-Key", "")
        authorization = self.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        return any(hmac.compare_digest(str(supplied), str(token)) for token in tokens)

    def _public_feed_url(self, url, fmt):
        """The URL a reader uses to fetch this feed; never carries API tokens."""
        return public_feed_url(self.settings, url, fmt)

    def _may_force_refresh(self):
        """``?refresh=1`` is honoured for loopback clients or token-authenticated calls.

        A signature does not cover ``refresh``, so signed links never force one.
        """
        if self._tokens():
            return self._authorized()
        return self._is_loopback()

    def _is_loopback(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

    def _home_allowed(self):
        """Whether this client may preview feeds and get links from ``/``.

        An open server allows everyone. With API tokens the caller must send
        one; with only a signing key, minting signed links is limited to the
        operator on this machine, as ``newsworker feed-url`` is.
        """
        if self._tokens():
            return self._authorized()
        if self._signing_key():
            return self._is_loopback()
        return True

    def _client_identity(self):
        if getattr(self.settings, "trust_proxy_client_ip", False):
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",", 1)[0].strip()
        return self.client_address[0]

    def _prepare(self, *, protected=False, feed=False, signed=False):
        self.request_id = self.headers.get("X-Request-ID", "").strip()[:128] or uuid.uuid4().hex
        if protected and not (signed or self._authorized(feed=feed)):
            self._problem(401, "Unauthorized", "A valid API token or feed signature is required")
            return False
        limiter = getattr(self.server, "rate_limiter", None)
        if limiter is None:
            limiter = TokenBucketLimiter(
                getattr(self.settings, "rate_limit_per_minute", 0),
                getattr(self.settings, "rate_limit_burst", 20),
            )
            self.server.rate_limiter = limiter  # type: ignore[attr-defined]
        allowed, retry_after = limiter.allow(self._client_identity())
        if not allowed:
            if _PROM_AVAILABLE:
                RATE_LIMITED.inc()
            self._problem(429, "Too Many Requests", f"Retry after {retry_after} seconds")
            return False
        return True

    def do_OPTIONS(self):
        self.request_id = uuid.uuid4().hex
        origin = self.headers.get("Origin")
        allowed = getattr(self.settings, "cors_allowed_origins", []) or []
        if origin not in allowed:
            self._problem(403, "Forbidden", "Origin is not allowed")
            return
        self.send_response(204)
        for key, value in self._request_headers("text/plain").items():
            self.send_header(key, value)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, X-API-Key, Content-Type")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        protected = path in {"/feed", "/metrics"}
        feed = path == "/feed"
        signed = feed and self._signed(parse_qs(parsed.query))
        if not self._prepare(protected=protected, feed=feed, signed=signed):
            return
        if path in {"/health", "/health/live"}:
            self._send_text(
                200,
                json.dumps({"status": "live", "version": __version__}),
                "application/json; charset=utf-8",
            )
        elif path == "/health/ready":
            self._handle_readiness()
        elif path == "/":
            self._handle_home(parse_qs(parsed.query))
        elif path == "/metrics":
            self._handle_metrics()
        elif path == "/feed":
            self._handle_feed(parse_qs(parsed.query))
        else:
            self._problem(404, "Not Found", f"Unknown path {parsed.path}")

    def _handle_readiness(self):
        try:
            cache_dir = self.settings.resolved_cache_dir()
            os.makedirs(cache_dir, exist_ok=True)
            if not os.access(cache_dir, os.R_OK | os.W_OK):
                raise OSError("cache directory is not readable and writable")
            semaphore = getattr(self.server, "build_semaphore", None)
            status = {
                "status": "ready",
                "version": __version__,
                "cache": {
                    "directory": cache_dir,
                    "content": self.service.content_cache.stats()
                    if hasattr(self.service, "content_cache")
                    else None,
                    "specs": self.service.spec_cache.stats()
                    if hasattr(self.service, "spec_cache")
                    else None,
                },
                "workers": {
                    "limit": getattr(self.settings, "max_concurrent_builds", 8),
                    "available": getattr(semaphore, "_value", None),
                },
            }
            self._send_text(200, json.dumps(status), "application/json; charset=utf-8")
        except Exception:
            self._problem(503, "Not Ready", "Runtime resources are unavailable")

    def _handle_metrics(self):
        if not _PROM_AVAILABLE or not getattr(self.settings, "metrics_enabled", True):
            self._problem(404, "Not Found", "Metrics are not enabled")
            return
        self._send_text(200, generate_latest().decode("utf-8"), CONTENT_TYPE_LATEST)

    def _handle_home(self, params):
        if "text/html" not in self.headers.get("Accept", ""):
            self._send_text(200, INDEX_TEXT)
            return
        url, fmt = _feed_request(params)
        if "format" not in params:
            fmt = "rss"
        allowed = self._home_allowed()
        feed = public_url = error = None
        if url and allowed:
            try:
                if fmt not in SUPPORTED_FORMATS:
                    raise _Problem(400, "Unsupported Format", "Choose one of the listed formats")
                self._check_source(url)
                feed, _diagnostics, start = self._build_feed(url)
                self._record_metric("200", start)
                public_url = self._public_feed_url(url, fmt)
            except _Problem as problem:
                error = problem
        page = _home_page(url, fmt, allowed=allowed, feed=feed, public_url=public_url, error=error)
        self._send_text(
            error.status if error is not None else 200,
            page,
            "text/html; charset=utf-8",
            {"Content-Security-Policy": HOME_CSP, "Cache-Control": "no-store"},
        )

    def _check_source(self, url):
        if not url:
            raise _Problem(400, "Bad Request", "Missing required 'url' query parameter")
        try:
            validate_url(url, allowed_hosts=getattr(self.settings, "allowed_hosts", []))
        except ValueError as exc:
            raise _Problem(400, "Rejected URL", str(exc)) from exc

    def _build_feed(self, url, force_refresh=False):
        """Build ``url`` under the server's worker limit: ``(feed, diagnostics, start)``."""
        semaphore = getattr(self.server, "build_semaphore", None)
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(
                getattr(self.settings, "max_concurrent_builds", 8)
            )
            self.server.build_semaphore = semaphore  # type: ignore[attr-defined]
        if not semaphore.acquire(blocking=False):
            self._record_metric("503", time.time())
            raise _Problem(503, "Service Unavailable", "Feed workers are saturated")
        start = time.time()
        if _PROM_AVAILABLE:
            ACTIVE_BUILDS.inc()
        try:
            if hasattr(self.service, "get_feed_with_diagnostics"):
                feed, diagnostics = self.service.get_feed_with_diagnostics(
                    url, force_refresh=force_refresh
                )
            else:
                feed = self.service.get_feed(url, force_refresh=force_refresh)
                diagnostics = None
        except Exception as exc:
            log.exception("Feed build failed request_id=%s url=%s", self.request_id, url)
            self._record_metric("502", start)
            raise _Problem(502, "Upstream Feed Failure", type(exc).__name__) from exc
        finally:
            semaphore.release()
            if _PROM_AVAILABLE:
                ACTIVE_BUILDS.dec()
        return feed, diagnostics, start

    def _handle_feed(self, params):
        url, fmt = _feed_request(params)
        try:
            self._check_source(url)
        except _Problem as problem:
            self._problem(problem.status, problem.title, problem.detail)
            return
        if fmt not in SUPPORTED_FORMATS:
            self._problem(
                400, "Unsupported Format", f"Supported formats: {', '.join(SUPPORTED_FORMATS)}"
            )
            return
        force_refresh = params.get("refresh", ["0"])[0].lower() in {"1", "true", "yes"}
        refresh_ignored = force_refresh and not self._may_force_refresh()
        if refresh_ignored:
            # An anonymous remote client must not be able to make this server
            # re-fetch third-party pages on demand (cache bypass amplification).
            force_refresh = False
        try:
            feed, diagnostics, start = self._build_feed(url, force_refresh)
        except _Problem as problem:
            self._problem(problem.status, problem.title, problem.detail)
            return
        try:
            public_url = self._public_feed_url(url, fmt)
            rendered = format_feed(feed, fmt=fmt, public_url=public_url)
            fingerprint = content_fingerprint(feed, fmt=fmt, public_url=public_url)
            newest = newest_pubdate(feed)
        except Exception as exc:
            log.exception("Feed rendering failed request_id=%s url=%s", self.request_id, url)
            self._record_metric("502", start)
            self._problem(502, "Upstream Feed Failure", type(exc).__name__)
            return
        # Weak validator: equal for every rendering of the same items, even when a
        # format embeds incidental bytes. Readers use it with If-None-Match.
        etag = 'W/"%s"' % fingerprint[:40]
        if _etag_matches(self.headers.get("If-None-Match", ""), etag):
            self._record_metric("304", start)
            self._send_not_modified(etag)
            return
        extra = {
            "ETag": etag,
            "Cache-Control": "%s, max-age=%d"
            % (
                "private" if self._tokens() else "public",
                max(0, getattr(self.settings, "content_ttl", 0)),
            ),
        }
        if newest is not None:
            extra["Last-Modified"] = formatdate(newest.timestamp(), usegmt=True)
        if refresh_ignored:
            extra["Warning"] = '299 newsworker "refresh ignored for unauthenticated remote clients"'
        if params.get("diagnostics", ["0"])[0].lower() in {"1", "true", "yes"}:
            if diagnostics is not None:
                extra["X-Newsworker-Confidence"] = f"{diagnostics.confidence:.3f}"
            if diagnostics is not None and diagnostics.warnings:
                extra["X-Newsworker-Warnings"] = str(len(diagnostics.warnings))
        self._record_metric("200", start)
        self._send_text(200, rendered, CONTENT_TYPES.get(fmt, "text/plain; charset=utf-8"), extra)

    @staticmethod
    def _record_metric(status, start):
        if _PROM_AVAILABLE:
            FEED_REQUESTS.labels(status=status).inc()
            FEED_LATENCY.observe(max(0, time.time() - start))


def run_server(settings=None):
    settings = settings or Settings()
    settings.validate()
    if (
        settings.host not in {"127.0.0.1", "localhost", "::1"}
        and not settings.api_tokens
        and not settings.feed_signing_key
    ):
        log.warning("Server is binding a routable host without API tokens or a feed signing key")
    server = ThreadingHTTPServer((settings.host, settings.port), FeedRequestHandler)
    server.feed_service = FeedService(settings=settings)  # type: ignore[attr-defined]
    server.rate_limiter = TokenBucketLimiter(
        settings.rate_limit_per_minute, settings.rate_limit_burst
    )  # type: ignore[attr-defined]
    server.build_semaphore = threading.BoundedSemaphore(settings.max_concurrent_builds)  # type: ignore[attr-defined]
    base = "http://%s:%d" % (settings.host, settings.port)
    print("newsworker feed server listening on %s" % base)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down feed server.")
    finally:
        server.server_close()

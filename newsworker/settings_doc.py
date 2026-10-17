"""One-line documentation for every setting, and the reference page built from it.

``python -m newsworker.settings_doc`` rewrites
``docs/docs/guides/settings-reference.md``; ``tests/test_settings_reference.py``
fails when a setting has no entry here or the page is out of date.
"""

from __future__ import annotations

import dataclasses
import json

from .settings import _SECRET_FIELDS, DEFAULT_HOME, ENV_PREFIX, Settings

#: Groups in the order they appear in the reference, each ``name: description``.
SETTINGS_HELP: dict[str, dict[str, str]] = {
    "Caching": {
        "cache_dir": "Directory for cached specs, page content and the watch store.",
        "content_ttl": "Seconds a cached page stays fresh; after that it is revalidated.",
        "spec_ttl": "Seconds a cached spec stays valid (0 = never expires).",
        "content_cache_max_entries": "Maximum cached pages on disk (0 = unbounded).",
        "content_cache_max_bytes": "Maximum total size of cached pages in bytes (0 = unbounded).",
        "spec_cache_max_entries": "Maximum cached specs on disk (0 = unbounded).",
    },
    "Fetching": {
        "user_agent": "User-Agent sent with every request.",
        "request_timeout": "Timeout of one HTTP request, in seconds.",
        "max_content_bytes": "Largest response body accepted, in bytes.",
        "verify_tls": "Verify TLS certificates.",
        "legacy_tls_ciphers": (
            "Also offer TLS 1.2 ciphers without forward secrecy (static RSA key exchange) "
            "for servers that accept nothing else; certificates are still verified."
        ),
        "respect_robots": "Honour robots.txt, including `Crawl-delay` and `Request-rate`.",
        "proxy": "Proxy URL for outgoing requests (empty = direct).",
        "trust_env_proxy": "Honour `HTTP(S)_PROXY`, `NO_PROXY` and `.netrc` from the environment.",
        "extra_headers": (
            "Extra headers for source pages; never sent to delivery endpoints and "
            "dropped on cross-origin redirects."
        ),
        "cookies_file": "Netscape/Mozilla cookie jar used for source pages.",
        "use_async": "Use the aiohttp transport for `batch` (needs the `async` extra).",
    },
    "Network policy": {
        "block_private_hosts": (
            "Refuse loopback, private, link-local, multicast and reserved addresses, "
            "checked again when the connection opens."
        ),
        "allowed_hosts": "Only these hosts may be fetched (empty = any public host).",
        "allow_private_hosts": "Allow private addresses for hosts listed in `allowed_hosts`.",
        "redirect_limit": "Maximum redirects followed per request.",
        "trusted_proxy": (
            "The configured proxy resolves host names itself, so local address checks are skipped."
        ),
        "delivery_max_response_bytes": "Largest response read from a delivery endpoint.",
    },
    "Politeness": {
        "per_host_concurrency": (
            "Requests in flight per site across all workers of the process (0 = unlimited)."
        ),
        "per_host_delay": (
            "Minimum seconds between requests to one site; robots.txt `Crawl-delay` raises it."
        ),
        "max_host_wait": (
            "Longest wait, in seconds, for a slot or a `Retry-After` window before the "
            "request fails as rate limited."
        ),
    },
    "Extraction": {
        "filtered_text_length": "Longest text node considered as a date candidate.",
        "default_language": "Feed language to report instead of detecting it.",
        "default_timezone": "IANA time zone for dates printed without an offset.",
        "structured_data": "Use JSON-LD and microdata article lists when the page has them.",
        "native_feeds": "Read RSS, Atom and JSON Feed responses as feeds.",
        "full_text": "Fetch every item link and store the article body (`fulltext` extra).",
        "full_text_workers": "Concurrent fetches for full text.",
        "bridges_dir": "Directory of user site bridges (empty = `~/.newsworker/bridges`).",
        "undated_fallback": "Try the conservative undated-listing fallback when no dates are found.",
        "undated_min_items": "Fewest repeated cards the undated fallback accepts.",
        "undated_min_confidence": "Lowest confidence (0–1) the undated fallback accepts.",
    },
    "Browser rendering": {
        "render": "Render every page in a headless browser (`browser` extra).",
        "render_fallback": (
            "Render only when nothing was found and the page looks client-rendered."
        ),
        "render_timeout": "Seconds allowed for one page render.",
        "render_concurrency": "Pages rendered at the same time.",
        "render_max_bytes": "Largest rendered document accepted, in bytes.",
    },
    "Feed server": {
        "host": "Interface `serve` binds to.",
        "port": "Port `serve` listens on.",
        "api_tokens": "Tokens accepted on `/feed` and `/metrics` (empty = no token required).",
        "feed_signing_key": (
            "Key for signed `/feed` links (`newsworker feed-url`); at least 16 characters. "
            "Setting it makes `/feed` require a token or a signature."
        ),
        "public_base_url": (
            "Base URL readers use to reach the server, for self links and `feed-url`."
        ),
        "rate_limit_per_minute": "Requests per minute per client (0 = no limit).",
        "rate_limit_burst": "Requests a client may make at once before the rate limit applies.",
        "max_concurrent_builds": "Feeds built at the same time; more requests get `503`.",
        "cors_allowed_origins": "Origins allowed to call the server from a browser.",
        "trust_proxy_client_ip": (
            "Identify clients by `X-Forwarded-For` (only behind a trusted reverse proxy)."
        ),
        "metrics_enabled": "Serve Prometheus metrics at `/metrics` (`metrics` extra).",
    },
    "Watch and delivery": {
        "watch_interval": "Seconds between polls of `watch`.",
        "watch_max_pages": "Pages followed per poll.",
        "delivery_retries": "Attempts before a delivery is marked terminal.",
        "delivery_backoff": "Base seconds of the exponential retry backoff.",
        "delivered_retention_days": "Days delivered outbox records are kept.",
        "history_retention_days": "Days item history is kept after an item was last seen (0 = forever).",
        "smtp_host": "SMTP server for the `smtp` channel.",
        "smtp_port": "SMTP port.",
        "smtp_username": "SMTP login.",
        "smtp_password": "SMTP password.",
        "smtp_from": "Sender address of `smtp` messages.",
        "telegram_token": "Bot token for the `telegram` channel.",
        "slack_webhook_url": "Incoming-webhook URL for the `slack` channel.",
        "discord_webhook_url": "Webhook URL for the `discord` channel.",
        "matrix_homeserver": "Homeserver URL for the `matrix` channel.",
        "matrix_token": "Access token for the `matrix` channel.",
        "matrix_room": "Room id for the `matrix` channel, e.g. `!abc:example.org`.",
        "mastodon_instance": "Instance URL for the `mastodon` channel.",
        "mastodon_token": "Access token with `write:statuses` for the `mastodon` channel.",
        "mastodon_visibility": "Post visibility: `public`, `unlisted`, `private` or `direct`.",
    },
}


def public_fields() -> list[str]:
    return [f.name for f in dataclasses.fields(Settings) if not f.name.startswith("_")]


def _default(name: str) -> str:
    value = getattr(Settings(), name)
    if name == "cache_dir":
        value = value.replace(DEFAULT_HOME, "~/.newsworker")
    if name == "user_agent":
        return "`newsworker/<version> (+https://github.com/ivbeg/newsworker)`"
    if isinstance(value, str):
        return f"`{value}`" if value else "—"
    return f"`{json.dumps(value)}`"


def settings_markdown() -> str:
    """The settings reference, one table per group."""
    parts = []
    for group, entries in SETTINGS_HELP.items():
        parts.append(f"## {group}\n")
        parts.append("| Setting | Default | Description |")
        parts.append("| --- | --- | --- |")
        for name, text in entries.items():
            secret = " Secret: redacted in output." if name in _SECRET_FIELDS else ""
            env = f"`{ENV_PREFIX}{name.upper()}`"
            parts.append(f"| `{name}`<br/>{env} | {_default(name)} | {text}{secret} |")
        parts.append("")
    return "\n".join(parts)


PAGE_HEADER = """---
title: "Settings reference"
description: "Every setting with its default, environment variable and meaning"
---

# Settings reference

Every setting can be set in the YAML settings file, as an environment variable
(shown under each name) or, for many, with a command-line option. Precedence is
defaults < YAML < environment < command line; see
[runtime configuration](/guides/runtime-configuration). Secret settings are
redacted wherever configuration is printed.

<!-- Generated by `python -m newsworker.settings_doc`; do not edit by hand. -->
"""


if __name__ == "__main__":  # pragma: no cover
    from pathlib import Path

    target = Path(__file__).resolve().parents[1] / "docs/docs/guides/settings-reference.md"
    target.write_text(PAGE_HEADER + settings_markdown(), encoding="utf-8")
    print(f"Wrote {target}")

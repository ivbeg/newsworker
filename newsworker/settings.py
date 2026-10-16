#!/usr/bin/env python
"""Layered, validated and secret-aware runtime configuration."""

from __future__ import annotations

import dataclasses
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union, get_args, get_origin, get_type_hints
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


def _default_user_agent() -> str:
    from . import __version__

    return f"newsworker/{__version__} (+https://github.com/ivbeg/newsworker)"


#: An honest, identifiable agent: robots.txt rules for "newsworker" apply to it,
#: and site owners can see who is fetching. Several sites reject the browser
#: string used before 1.4 as an impersonation attempt.
DEFAULT_USER_AGENT = _default_user_agent()
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".newsworker")
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_HOME, "config.yaml")
ENV_PREFIX = "NEWSWORKER_"
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_SECRET_FIELDS = {
    "api_tokens",
    "feed_signing_key",
    "cookies_file",
    "proxy",
    "smtp_password",
    "telegram_token",
    "slack_webhook_url",
    "discord_webhook_url",
    "matrix_token",
}


class SettingsError(ValueError):
    """Raised when merged runtime configuration is invalid."""


@dataclass
class Settings:
    cache_dir: str = os.path.join(DEFAULT_HOME, "cache")
    content_ttl: int = 3600
    spec_ttl: int = 0
    content_cache_max_entries: int = 0
    content_cache_max_bytes: int = 0
    spec_cache_max_entries: int = 0
    host: str = "127.0.0.1"
    port: int = 8787
    user_agent: str = DEFAULT_USER_AGENT
    filtered_text_length: int = 150
    max_content_bytes: int = 10 * 1024 * 1024
    verify_tls: bool = True
    respect_robots: bool = True
    request_timeout: int = 30
    proxy: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)
    cookies_file: str = ""
    default_language: str = ""
    default_timezone: str = "UTC"
    full_text: bool = False
    full_text_workers: int = 4
    allowed_hosts: List[str] = field(default_factory=list)
    bridges_dir: str = ""
    use_async: bool = False

    # Shared network policy.
    block_private_hosts: bool = True
    allow_private_hosts: bool = False
    redirect_limit: int = 5
    trusted_proxy: bool = False
    # Read HTTP(S)_PROXY / NO_PROXY / .netrc from the environment (off by default).
    trust_env_proxy: bool = False
    # Politeness towards crawled sites (shared by every worker in the process):
    # requests in flight per host (0 = unlimited), minimum seconds between
    # request starts (robots.txt Crawl-delay raises it), and the longest wait
    # for a slot or a Retry-After window before giving up.
    per_host_concurrency: int = 2
    per_host_delay: float = 0.0
    max_host_wait: float = 30.0
    delivery_max_response_bytes: int = 1024 * 1024

    # Server controls.
    api_tokens: List[str] = field(default_factory=list)
    rate_limit_per_minute: int = 0
    rate_limit_burst: int = 20
    max_concurrent_builds: int = 8
    cors_allowed_origins: List[str] = field(default_factory=list)
    trust_proxy_client_ip: bool = False
    metrics_enabled: bool = False
    # Externally visible base URL of the feed server (for rel="self" links),
    # e.g. "https://feeds.example.org". Defaults to http://host:port.
    public_base_url: str = ""
    # Secret for signed /feed links (``newsworker feed-url``): a valid ``sig``
    # authorises that one source URL and format, for readers that cannot send
    # an API token. Setting it also makes /feed require a token or signature.
    feed_signing_key: str = ""

    # Watch/outbox and delivery.
    watch_interval: float = 300.0
    watch_max_pages: int = 1
    delivery_retries: int = 3
    delivery_backoff: float = 1.0
    delivered_retention_days: int = 30
    # Item history kept by watch (0 = keep forever).
    history_retention_days: int = 365
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    telegram_token: str = ""
    # Chat channels for watch (select with --channel slack|discord|matrix).
    slack_webhook_url: str = ""
    discord_webhook_url: str = ""
    matrix_homeserver: str = ""
    matrix_token: str = ""
    matrix_room: str = ""

    # Optional extraction strategies.
    render: bool = False
    render_fallback: bool = False
    # Use JSON-LD / microdata article lists (exact dates) when present.
    structured_data: bool = True
    # Read RSS/Atom/JSON Feed responses as feeds instead of HTML pages.
    native_feeds: bool = True
    render_timeout: int = 15
    render_concurrency: int = 1
    render_max_bytes: int = 10 * 1024 * 1024
    undated_fallback: bool = False
    undated_min_items: int = 3
    undated_min_confidence: float = 0.75

    _resolved: bool = field(default=False, repr=False, compare=False)
    _sources: Dict[str, str] = field(default_factory=dict, repr=False, compare=False)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_resolved", False) and name not in {"_resolved", "_sources"}:
            raise dataclasses.FrozenInstanceError(
                f"Resolved settings are immutable; cannot assign {name!r}"
            )
        super().__setattr__(name, value)

    def to_dict(self, *, redact: bool = False) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("_resolved", None)
        data.pop("_sources", None)
        if redact:
            data = redact_settings(data)
        return data

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> Settings:
        data = data or {}
        known = {f.name for f in dataclasses.fields(cls) if not f.name.startswith("_")}
        return cls(**{key: value for key, value in data.items() if key in known})

    @classmethod
    def load(cls, path: Optional[str] = None) -> Settings:
        path = path or DEFAULT_CONFIG_PATH
        if not os.path.exists(path):
            settings = cls()
            try:
                settings.save(path)
            except OSError:
                pass
            return settings
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(yaml.safe_load(handle) or {})

    @classmethod
    def resolve(
        cls,
        path: Optional[str] = None,
        *,
        environ: Optional[Mapping[str, str]] = None,
        cli: Optional[Mapping[str, Any]] = None,
        create_default: bool = False,
    ) -> Settings:
        """Resolve defaults < YAML < environment < explicit CLI options."""
        defaults = cls().to_dict()
        merged: Dict[str, Any] = dict(defaults)
        sources = {key: "default" for key in defaults}
        config_path = path or DEFAULT_CONFIG_PATH
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as handle:
                file_values = yaml.safe_load(handle) or {}
            if not isinstance(file_values, dict):
                raise SettingsError("configuration root must be a mapping")
            _merge_known(merged, sources, file_values, "yaml")
        elif create_default:
            cls().save(config_path)

        env_values = _environment_values(environ or os.environ, cls)
        _merge_known(merged, sources, env_values, "environment")
        explicit = {key: value for key, value in (cli or {}).items() if value is not None}
        _merge_known(merged, sources, explicit, "cli")
        settings = cls.from_dict(merged)
        settings._sources = sources
        settings.validate()
        settings._resolved = True
        return settings

    def validate(self) -> None:
        positive = {
            "filtered_text_length": self.filtered_text_length,
            "max_content_bytes": self.max_content_bytes,
            "request_timeout": self.request_timeout,
            "full_text_workers": self.full_text_workers,
            "delivery_max_response_bytes": self.delivery_max_response_bytes,
            "rate_limit_burst": self.rate_limit_burst,
            "max_concurrent_builds": self.max_concurrent_builds,
            "watch_interval": self.watch_interval,
            "watch_max_pages": self.watch_max_pages,
            "delivery_retries": self.delivery_retries,
            "delivery_backoff": self.delivery_backoff,
            "delivered_retention_days": self.delivered_retention_days,
            "render_timeout": self.render_timeout,
            "render_concurrency": self.render_concurrency,
            "render_max_bytes": self.render_max_bytes,
            "undated_min_items": self.undated_min_items,
        }
        for name, value in positive.items():
            if value <= 0:
                raise SettingsError(
                    f"{name} must be positive (from {self._sources.get(name, 'value')})"
                )
        nonnegative = {
            "content_ttl": self.content_ttl,
            "spec_ttl": self.spec_ttl,
            "content_cache_max_entries": self.content_cache_max_entries,
            "content_cache_max_bytes": self.content_cache_max_bytes,
            "spec_cache_max_entries": self.spec_cache_max_entries,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "redirect_limit": self.redirect_limit,
            "per_host_concurrency": self.per_host_concurrency,
            "per_host_delay": self.per_host_delay,
            "max_host_wait": self.max_host_wait,
            "history_retention_days": self.history_retention_days,
        }
        for name, value in nonnegative.items():
            if value < 0:
                raise SettingsError(f"{name} must not be negative")
        if self.feed_signing_key and len(self.feed_signing_key) < 16:
            raise SettingsError("feed_signing_key must be at least 16 characters")
        if not 1 <= int(self.port) <= 65535:
            raise SettingsError("port must be between 1 and 65535")
        if not 1 <= int(self.smtp_port) <= 65535:
            raise SettingsError("smtp_port must be between 1 and 65535")
        if not 0.0 <= float(self.undated_min_confidence) <= 1.0:
            raise SettingsError("undated_min_confidence must be between 0 and 1")
        try:
            ZoneInfo(self.default_timezone)
        except ZoneInfoNotFoundError as exc:
            raise SettingsError(f"unknown default_timezone {self.default_timezone!r}") from exc
        if self.proxy:
            parsed = urlsplit(self.proxy)
            if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname:
                raise SettingsError("proxy must be an absolute supported proxy URL")
        for name, header_value in self.extra_headers.items():
            if not name or not _HEADER_NAME.fullmatch(str(name)):
                raise SettingsError(f"invalid HTTP header name {name!r}")
            if "\r" in str(header_value) or "\n" in str(header_value):
                raise SettingsError(f"invalid newline in HTTP header {name!r}")
        for host in self.allowed_hosts:
            if not str(host).strip() or "://" in str(host) or "/" in str(host):
                raise SettingsError(f"invalid allowed host {host!r}")
        for origin in self.cors_allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise SettingsError(f"invalid CORS origin {origin!r}")
        if self.cookies_file:
            path = Path(self.cookies_file).expanduser()
            if not path.is_file():
                raise SettingsError(f"cookies_file is not a readable file: {path}")

    def save(self, path: Optional[str] = None) -> None:
        path = path or DEFAULT_CONFIG_PATH
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(self.to_dict(), handle, sort_keys=False, allow_unicode=True)

    def resolved_cache_dir(self) -> str:
        return os.path.expanduser(self.cache_dir)

    def source_for(self, field_name: str) -> str:
        return self._sources.get(field_name, "unknown")


def _merge_known(
    target: Dict[str, Any], sources: Dict[str, str], values: Mapping[str, Any], source: str
) -> None:
    for key, value in values.items():
        if key in target and not key.startswith("_"):
            target[key] = value
            sources[key] = source


def _environment_values(environ: Mapping[str, str], cls: type[Settings]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    hints = get_type_hints(cls)
    for field_info in dataclasses.fields(cls):
        name = field_info.name
        if name.startswith("_"):
            continue
        env_name = ENV_PREFIX + name.upper()
        if env_name not in environ:
            continue
        try:
            result[name] = _parse_env_value(environ[env_name], hints.get(name, str))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SettingsError(f"invalid {env_name}: {exc}") from exc
    return result


def _parse_env_value(raw: str, annotation: Any) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if annotation is bool:
        value = raw.strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        if value in {"0", "false", "no", "off"}:
            return False
        raise ValueError("expected true/false")
    if annotation is int:
        return int(raw)
    if annotation is float:
        return float(raw)
    if origin in {list, List}:
        if raw.lstrip().startswith("["):
            value = json.loads(raw)
            if not isinstance(value, list):
                raise ValueError("expected JSON list")
            return value
        return [part.strip() for part in raw.split(",") if part.strip()]
    if origin in {dict, Dict}:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return {str(key): str(item) for key, item in value.items()}
    if origin is Union and type(None) in args:
        inner = next(arg for arg in args if arg is not type(None))
        return _parse_env_value(raw, inner)
    return raw


def _redacted(value: Any) -> str:
    return "<redacted>" if value not in (None, "", [], {}) else ""


def redact_settings(data: Mapping[str, Any]) -> Dict[str, Any]:
    safe = dict(data)
    for name in _SECRET_FIELDS:
        if name in safe:
            safe[name] = _redacted(safe[name])
    if "extra_headers" in safe:
        headers = {}
        for key, value in dict(safe["extra_headers"] or {}).items():
            headers[key] = (
                _redacted(value)
                if key.lower()
                in {
                    "authorization",
                    "cookie",
                    "proxy-authorization",
                    "x-api-key",
                }
                else value
            )
        safe["extra_headers"] = headers
    return safe

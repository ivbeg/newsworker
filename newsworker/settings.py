#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Settings for the newsworker local feed server and caching layer.

The settings capture where cached parsing specs and page content are stored,
how long fetched page content stays fresh, and how the local HTTP server binds.

A settings file is a small YAML document, by default located at
``~/.newsworker/config.yaml``. When the file is missing it is created with the
default values on first load so users have a template to edit.
"""

import os
from dataclasses import dataclass, asdict

import yaml

#: Default User-Agent used for outgoing HTTP requests.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) "
    "Chrome/23.0.1271.64 Safari/537.11"
)

#: Root directory holding the default config file and cache.
DEFAULT_HOME = os.path.join(os.path.expanduser("~"), ".newsworker")

#: Default path of the YAML settings file.
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_HOME, "config.yaml")


@dataclass
class Settings:
    """Runtime settings for caching and the local feed server."""

    #: Directory where cached specs and page content are stored.
    cache_dir: str = os.path.join(DEFAULT_HOME, "cache")
    #: Seconds a cached page stays fresh before being re-fetched.
    content_ttl: int = 3600
    #: Seconds a cached spec stays valid; ``0`` means it never expires.
    spec_ttl: int = 0
    #: Host interface the local server binds to.
    host: str = "127.0.0.1"
    #: TCP port the local server listens on.
    port: int = 8787
    #: User-Agent used for outgoing HTTP requests.
    user_agent: str = DEFAULT_USER_AGENT
    #: Maximum text length considered when detecting date-bearing nodes.
    filtered_text_length: int = 150

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def load(cls, path=None):
        """Loads settings from ``path`` (or the default location).

        When the file does not exist it is created with the defaults so the
        user has an editable template, and the defaults are returned.
        """
        path = path or DEFAULT_CONFIG_PATH
        if not os.path.exists(path):
            settings = cls()
            try:
                settings.save(path)
            except OSError:
                # A read-only home directory should not break loading.
                pass
            return settings
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return cls.from_dict(data)

    def save(self, path=None):
        """Writes the settings as YAML to ``path`` (or the default location)."""
        path = path or DEFAULT_CONFIG_PATH
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                self.to_dict(), handle, sort_keys=False, allow_unicode=True
            )

    def resolved_cache_dir(self):
        """Returns the cache directory with ``~`` expanded."""
        return os.path.expanduser(self.cache_dir)

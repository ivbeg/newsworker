#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
File-based caches for parsing specs and fetched page content.

Both caches key entries by a SHA-1 hash of the source URL and store one file
per entry under a cache directory. Freshness is tracked via the file
modification time, so no separate metadata files are needed.

* :class:`SpecCache` stores serialized :class:`newsworker.spec.FeedSpec`
  documents. Specs are expensive to build (they run the dynamic heuristics), so
  by default they never expire (``ttl == 0``).
* :class:`ContentCache` stores raw page bytes with a configurable TTL so the
  same page is not re-fetched on every request.
"""

import hashlib
import os
import time

from .spec import FeedSpec


def key_for(url):
    """Returns a stable filesystem-safe key for ``url``."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _is_fresh(path, ttl):
    """Returns True when ``path`` exists and is within ``ttl`` seconds.

    A ``ttl`` of ``0`` (or negative) means entries never expire.
    """
    if not os.path.exists(path):
        return False
    if ttl and ttl > 0:
        age = time.time() - os.path.getmtime(path)
        if age > ttl:
            return False
    return True


class SpecCache:
    """Caches YAML parsing specs keyed by source URL."""

    def __init__(self, cache_dir, ttl=0):
        self.dir = os.path.join(cache_dir, "specs")
        self.ttl = ttl

    def _path(self, url):
        return os.path.join(self.dir, key_for(url) + ".yaml")

    def get(self, url):
        """Returns a :class:`FeedSpec` for ``url`` or ``None`` when missing/stale."""
        path = self._path(url)
        if not _is_fresh(path, self.ttl):
            return None
        try:
            return FeedSpec.load(path)
        except (OSError, ValueError):
            return None

    def set(self, url, spec):
        """Persists ``spec`` for ``url``."""
        os.makedirs(self.dir, exist_ok=True)
        spec.save(self._path(url))

    def path_for(self, url):
        """Returns the on-disk path used for ``url`` (may not exist yet)."""
        return self._path(url)


class ContentCache:
    """Caches raw fetched page bytes keyed by source URL."""

    def __init__(self, cache_dir, ttl=3600):
        self.dir = os.path.join(cache_dir, "content")
        self.ttl = ttl

    def _path(self, url):
        return os.path.join(self.dir, key_for(url) + ".bin")

    def get(self, url):
        """Returns cached bytes for ``url`` or ``None`` when missing/stale."""
        path = self._path(url)
        if not _is_fresh(path, self.ttl):
            return None
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            return None

    def set(self, url, data):
        """Stores raw ``data`` bytes for ``url``."""
        os.makedirs(self.dir, exist_ok=True)
        with open(self._path(url), "wb") as handle:
            handle.write(data)

    def path_for(self, url):
        """Returns the on-disk path used for ``url`` (may not exist yet)."""
        return self._path(url)

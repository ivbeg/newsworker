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

Both caches optionally bound their on-disk footprint: after every write, the
oldest entries (by modification time) are evicted until the number of files and
their total size fall back within the configured limits. A limit of ``0`` (the
default) disables that bound, preserving the previous unbounded behaviour.
"""

import glob
import hashlib
import json
import os
import tempfile
import threading
import time
from typing import Dict

from .spec import FeedSpec


def key_for(url):
    """Returns a stable filesystem-safe key for ``url``."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


# Per-path locks serialize concurrent writers to the same cache entry so a
# ``ThreadingHTTPServer`` worker cannot observe a half-written file.
_PATH_LOCKS: Dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _lock_for(path):
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[path] = lock
        return lock


def _atomic_write(path, data):
    """Writes ``data`` bytes to ``path`` via a temp file + atomic rename."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


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


def _evict(directory, pattern, max_entries=0, max_bytes=0):
    """Evicts the oldest files in ``directory`` matching ``pattern``.

    Files are removed (oldest modification time first) until both the entry
    count and the total byte size are within the given limits. A limit of ``0``
    (or negative) disables that particular bound.
    """
    if (not max_entries or max_entries <= 0) and (not max_bytes or max_bytes <= 0):
        return
    try:
        paths = glob.glob(os.path.join(directory, pattern))
    except OSError:
        return
    entries = []
    total = 0
    for path in paths:
        try:
            stat = os.stat(path)
        except OSError:
            continue
        entries.append((stat.st_mtime, stat.st_size, path))
        total += stat.st_size
    # Oldest first, so we evict least-recently-written entries.
    entries.sort()
    count = len(entries)
    i = 0
    while i < len(entries) and (
        (max_entries and max_entries > 0 and count > max_entries)
        or (max_bytes and max_bytes > 0 and total > max_bytes)
    ):
        _, size, path = entries[i]
        try:
            os.remove(path)
            count -= 1
            total -= size
        except OSError:
            pass
        i += 1


def _list_entries(directory, pattern):
    """Returns cached entries as ``[{path, bytes, mtime}]`` sorted oldest-first."""
    result = []
    try:
        paths = glob.glob(os.path.join(directory, pattern))
    except OSError:
        return result
    for path in paths:
        try:
            stat = os.stat(path)
        except OSError:
            continue
        result.append({"path": path, "bytes": stat.st_size, "mtime": stat.st_mtime})
    result.sort(key=lambda entry: entry["mtime"])
    return result


def _cache_stats(directory, pattern):
    """Returns ``{count, bytes, oldest, newest}`` for a cache directory."""
    entries = _list_entries(directory, pattern)
    return {
        "count": len(entries),
        "bytes": sum(entry["bytes"] for entry in entries),
        "oldest": entries[0]["mtime"] if entries else None,
        "newest": entries[-1]["mtime"] if entries else None,
    }


def _clear_dir(directory, pattern):
    """Removes all matching entries; returns the number removed."""
    removed = 0
    for entry in _list_entries(directory, pattern):
        try:
            os.remove(entry["path"])
            removed += 1
        except OSError:
            pass
    return removed


class _CacheStatsMixin:
    """Shared list/stats/clear operations for the file caches."""

    def list_entries(self):
        """Returns cached entries as ``[{path, bytes, mtime}]`` (oldest first)."""
        return _list_entries(self.dir, self.pattern)

    def stats(self):
        """Returns ``{count, bytes, oldest, newest}`` for this cache."""
        return _cache_stats(self.dir, self.pattern)

    def clear(self):
        """Removes every entry in this cache; returns the number removed."""
        return _clear_dir(self.dir, self.pattern)


class SpecCache(_CacheStatsMixin):
    """Caches YAML parsing specs keyed by source URL."""

    #: Glob pattern for entries in this cache.
    pattern = "*.yaml"

    def __init__(self, cache_dir, ttl=0, max_entries=0, max_bytes=0):
        self.dir = os.path.join(cache_dir, "specs")
        self.ttl = ttl
        self.max_entries = max_entries
        self.max_bytes = max_bytes

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
        """Persists ``spec`` for ``url`` and evicts old entries if over budget."""
        os.makedirs(self.dir, exist_ok=True)
        path = self._path(url)
        with _lock_for(path):
            tmp = path + ".tmp"
            spec.save(tmp)
            os.replace(tmp, path)
        _evict(self.dir, "*.yaml", self.max_entries, self.max_bytes)

    def path_for(self, url):
        """Returns the on-disk path used for ``url`` (may not exist yet)."""
        return self._path(url)


class ContentCache(_CacheStatsMixin):
    """Caches raw fetched page bytes keyed by source URL."""

    #: Glob pattern for entries in this cache.
    pattern = "*.bin"

    def __init__(self, cache_dir, ttl=3600, max_entries=0, max_bytes=0):
        self.dir = os.path.join(cache_dir, "content")
        self.ttl = ttl
        self.max_entries = max_entries
        self.max_bytes = max_bytes

    def _path(self, url):
        return os.path.join(self.dir, key_for(url) + ".bin")

    def _meta_path(self, url):
        return os.path.join(self.dir, key_for(url) + ".meta")

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

    def get_stale(self, url):
        """Returns cached bytes regardless of freshness, or ``None`` when absent.

        Used for conditional upstream revalidation: an expired entry can still be
        reused if the upstream responds ``304 Not Modified``.
        """
        path = self._path(url)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            return None

    def get_meta(self, url):
        """Returns stored upstream validators ``{etag, last_modified}`` or ``{}``."""
        try:
            with open(self._meta_path(url), "r", encoding="utf-8") as handle:
                return json.load(handle) or {}
        except (OSError, ValueError):
            return {}

    def touch(self, url):
        """Refreshes the freshness clock of an existing entry (mtime = now)."""
        path = self._path(url)
        if os.path.exists(path):
            now = time.time()
            try:
                os.utime(path, (now, now))
            except OSError:
                pass

    def set(self, url, data, meta=None):
        """Stores raw ``data`` bytes for ``url`` (atomically) plus optional
        upstream validators, and evicts old entries if over budget."""
        os.makedirs(self.dir, exist_ok=True)
        path = self._path(url)
        with _lock_for(path):
            _atomic_write(path, data)
            if meta:
                clean = {k: v for k, v in meta.items() if v}
                if clean:
                    _atomic_write(
                        self._meta_path(url),
                        json.dumps(clean).encode("utf-8"),
                    )
        _evict(self.dir, "*.bin", self.max_entries, self.max_bytes)

    def path_for(self, url):
        """Returns the on-disk path used for ``url`` (may not exist yet)."""
        return self._path(url)

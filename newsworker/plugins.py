#!/usr/bin/env python
"""Third-party extractor plugins loaded via setuptools entry points.

Packages register extractors under the ``newsworker.extractors`` entry-point group.
Each plugin exposes ``matches(url)`` and ``extract(url, data=None, **kwargs)`` returning
the internal feed dict.
"""

import logging
from typing import Any

from .model import Feed

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "newsworker.extractors"


class BaseExtractorPlugin:
    """Base class for third-party extractors (subclass and register via entry points)."""

    def matches(self, url: str) -> bool:
        """Return True when this plugin should handle ``url``."""
        raise NotImplementedError

    def extract(self, url: str, data: bytes | None = None, **kwargs: Any) -> Feed:
        """Return the feed for ``url`` (see :class:`newsworker.model.Feed`)."""
        raise NotImplementedError


def _load_entry_point(name, entry):
    try:
        loaded = entry.load()
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to load extractor plugin %r: %s", name, e)
        return None
    if isinstance(loaded, type):
        try:
            return loaded()
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to instantiate extractor plugin %r: %s", name, e)
            return None
    return loaded


def load_plugins(extra: list[Any] | None = None) -> list[Any]:
    """Returns all registered extractor plugins (entry points plus ``extra``)."""
    plugins: list[Any] = list(extra or [])
    try:
        from importlib.metadata import entry_points
    except ImportError:
        from importlib_metadata import entry_points  # type: ignore[no-redef]

    try:
        eps = entry_points()
        if hasattr(eps, "select"):
            group = eps.select(group=ENTRY_POINT_GROUP)
        else:
            group = eps.get(ENTRY_POINT_GROUP, ())  # type: ignore[union-attr, arg-type]
    except Exception as e:  # noqa: BLE001
        log.debug("Could not enumerate entry points: %s", e)
        return plugins

    for ep in group:
        plugin = _load_entry_point(ep.name, ep)
        if plugin is not None:
            plugins.append(plugin)
    return plugins


def select_plugin(url: str, plugins: list[Any]) -> Any | None:
    """Returns the first plugin whose ``matches(url)`` is true, or ``None``."""
    for plugin in plugins:
        try:
            if plugin.matches(url):
                return plugin
        except Exception as e:  # noqa: BLE001
            log.debug("Plugin %r matches() failed for %s: %s", plugin, url, e)
    return None

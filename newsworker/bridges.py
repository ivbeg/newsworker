#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Per-site bridge specs: YAML files with a host/path matcher plus a FeedSpec body.

Bridges live in ``newsworker/bridges/`` (bundled) and optionally in
``~/.newsworker/bridges/`` (user overrides). When a URL matches, the bridge spec is
applied via :class:`newsworker.spec.SpecExtractor` instead of running dynamic heuristics.
"""

import fnmatch
import glob
import logging
import os
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

import yaml

from .spec import FeedSpec

log = logging.getLogger(__name__)

_PACKAGE_BRIDGES = os.path.join(os.path.dirname(__file__), "bridges")


@dataclass
class SiteBridge:
    """A host/path matcher paired with a parsing spec."""

    host: str
    path_pattern: str = "*"
    spec: FeedSpec = None  # type: ignore[assignment]
    name: str = ""

    def matches(self, url: str) -> bool:
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        if self.host.startswith("*."):
            suffix = self.host[1:]
            if not (host == self.host[2:] or host.endswith(suffix)):
                return False
        elif host != self.host.lower():
            return False
        path = parsed.path or "/"
        return fnmatch.fnmatch(path, self.path_pattern)


def _bridge_from_dict(data, source_name=""):
    match = data.get("match") or {}
    host = match.get("host") or match.get("hosts")
    if isinstance(host, list):
        host = host[0] if host else ""
    if not host:
        raise ValueError("bridge missing match.host")
    spec_data = data.get("spec") or data.get("bridge") or data
    if "match" in spec_data:
        spec_data = {k: v for k, v in spec_data.items() if k != "match"}
    spec = FeedSpec.from_dict(spec_data)
    return SiteBridge(
        host=str(host),
        path_pattern=str(match.get("path") or "*"),
        spec=spec,
        name=source_name or str(host),
    )


def load_bridge_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return _bridge_from_dict(data, source_name=os.path.basename(path))


def load_bridges(*directories) -> List[SiteBridge]:
    """Loads all ``*.yaml`` / ``*.yml`` bridge files from ``directories`` (in order)."""
    bridges: List[SiteBridge] = []
    for directory in directories:
        if not directory or not os.path.isdir(directory):
            continue
        pattern = os.path.join(directory, "*.y*ml")
        for path in sorted(glob.glob(pattern)):
            try:
                bridges.append(load_bridge_file(path))
            except Exception as e:  # noqa: BLE001
                log.warning("Skipping bridge %s: %s", path, e)
    return bridges


def default_bridge_dirs(settings=None):
    """Returns bundled then user bridge directories."""
    from .settings import DEFAULT_HOME

    dirs = [_PACKAGE_BRIDGES]
    user_dir = os.path.join(DEFAULT_HOME, "bridges")
    if settings is not None and getattr(settings, "bridges_dir", ""):
        user_dir = os.path.expanduser(settings.bridges_dir)
    dirs.append(user_dir)
    return dirs


def select_bridge(url: str, bridges: List[SiteBridge]) -> Optional[FeedSpec]:
    """Returns the spec from the first matching bridge, or ``None``."""
    for bridge in bridges:
        try:
            if bridge.matches(url):
                return bridge.spec
        except Exception as e:  # noqa: BLE001
            log.debug("Bridge %r match failed for %s: %s", bridge.name, url, e)
    return None

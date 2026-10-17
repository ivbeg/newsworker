"""The feed and item shapes passed from extraction to output.

Every strategy (spec, dynamic, native feed, structured data, undated,
plugins) produces a :class:`Feed`, and every output format, delivery channel
and the MCP tools read one. The shapes are ``TypedDict`` so existing code keeps
using plain dictionaries while type checkers, plugins and formatters see one
contract. Keys are optional (``total=False``) because strategies fill
different subsets; the comments say which keys are always present.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, TypedDict


class ItemExtra(TypedDict, total=False):
    #: Every link found in the item block, absolute, http(s) only.
    links: list[str]
    #: Image URLs found in the item block.
    images: list[str]


class Item(TypedDict, total=False):
    """One news item. ``title``, ``description``, ``pubdate``, ``link`` and
    ``unique_id`` are always present (``pubdate``/``link`` may be ``None``)."""

    title: str | None
    description: str | None
    #: Timezone-aware UTC publication time; ``None`` for undated listings.
    pubdate: dt.datetime | None
    link: str | None
    #: Stable identity: from the native entry id, else the link, else the text.
    unique_id: str
    #: Hash of the visible content; changes when the item is edited.
    content_hash: str
    #: Entry id from a native RSS/Atom/JSON Feed source.
    native_id: str | None
    author: str
    categories: list[str]
    #: Full article body (``--fulltext`` or native feed content).
    content: str
    #: ``"html"`` or ``"text"``.
    content_kind: str
    #: HTML of the item block on the source page (HTML strategies only); used
    #: for author/category enrichment and kept in JSON/YAML output.
    raw_html: bytes | str
    #: Set by ``watch --deliver-updates`` on a changed item.
    updated: bool
    version: int
    extra: ItemExtra


class Feed(TypedDict, total=False):
    """A built feed. ``title``, ``link``, ``description``, ``language`` and
    ``items`` are always present."""

    title: str
    link: str
    description: str
    #: ISO 639-1 code or ``None`` when unknown.
    language: str | None
    items: list[Item]
    #: How the feed was produced (strategy, source kind, spec); for humans.
    provenance: dict[str, Any]
    #: ``"rss20"``, ``"atom10"``, ``"jsonfeed"`` … when the source was a feed.
    native_format: str
    #: Date patterns that matched (``{"pats": [...]}``); set by the low-level
    #: ``FeedExtractor.get_feed`` and reused to narrow the parser next time.
    cache: dict[str, Any]

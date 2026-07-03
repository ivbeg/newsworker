#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Output formatting for extracted feeds.

Converts the internal ``feed`` dictionary produced by
:class:`newsworker.extractor.FeedExtractor` and
:class:`newsworker.spec.SpecExtractor` into different serialization formats:

* ``json`` -- the raw internal representation (default);
* ``rss``  -- RSS 2.0 (via ``feedgen``);
* ``atom`` -- Atom 1.0 (via ``feedgen``);
* ``csv``  -- a flat comma-separated table of items.

The feed dictionary has the following shape::

    {
        "title": str,
        "language": str,
        "link": str,
        "description": str,
        "items": [
            {
                "title": str | None,
                "description": str | None,
                "pubdate": datetime | None,
                "unique_id": str,
                "link": str | None,
                "extra": {"links": [...], "images": [...]},
                ...
            },
            ...
        ],
    }
"""

import csv
import datetime
import io
import json
from xml.sax.saxutils import escape, quoteattr

#: Supported output format identifiers for extracted feeds.
SUPPORTED_FORMATS = ("json", "rss", "atom", "csv")

#: Supported output format identifiers for discovered feeds (``scan``).
SCAN_FORMATS = ("json", "rss", "atom", "csv", "opml")


def _date_handler(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return None


def _ensure_tz(value):
    """Returns a timezone-aware datetime (feedgen requires tzinfo).

    ``qddate`` yields naive datetimes; assume UTC when the timezone is missing.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(
            value.year, value.month, value.day, tzinfo=datetime.timezone.utc
        )
    return None


def _first_image(item):
    extra = item.get("extra") or {}
    images = extra.get("images") or []
    return images[0] if images else None


def to_json(feed):
    """Serializes ``feed`` to a pretty-printed JSON string."""
    return json.dumps(feed, indent=4, default=_date_handler, ensure_ascii=False)


def _build_feedgen(feed, public_url=None):
    from feedgen.feed import FeedGenerator

    fg = FeedGenerator()
    link = feed.get("link") or public_url or ""
    # Atom requires a feed id; RSS ignores it. Use the source link as a stable id.
    fg.id(link or (feed.get("title") or "newsworker"))
    fg.title(feed.get("title") or "News feed")
    fg.description(feed.get("description") or feed.get("title") or "News feed")
    if public_url:
        fg.link(href=public_url, rel="self")
    if link:
        fg.link(href=link, rel="alternate")
    if feed.get("language"):
        fg.language(feed["language"])

    for item in feed.get("items", []):
        entry = fg.add_entry()
        item_link = item.get("link")
        entry.id(item.get("unique_id") or item_link or item.get("title") or "")
        entry.title(item.get("title") or item.get("description") or "(no title)")
        if item.get("description"):
            entry.description(item["description"])
        if item_link:
            entry.link(href=item_link)
        pubdate = _ensure_tz(item.get("pubdate"))
        if pubdate is not None:
            entry.pubDate(pubdate)
            entry.updated(pubdate)
        image = _first_image(item)
        if image:
            entry.enclosure(image, 0, "image/jpeg")
    return fg


def to_rss(feed, public_url=None):
    """Serializes ``feed`` to an RSS 2.0 string."""
    fg = _build_feedgen(feed, public_url=public_url)
    return fg.rss_str(pretty=True).decode("utf-8")


def to_atom(feed, public_url=None):
    """Serializes ``feed`` to an Atom 1.0 string."""
    fg = _build_feedgen(feed, public_url=public_url)
    return fg.atom_str(pretty=True).decode("utf-8")


def to_csv(feed):
    """Serializes ``feed`` items to a CSV string."""
    buffer = io.StringIO()
    fieldnames = ["title", "link", "pubdate", "description", "image", "unique_id"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for item in feed.get("items", []):
        pubdate = item.get("pubdate")
        writer.writerow(
            {
                "title": item.get("title") or "",
                "link": item.get("link") or "",
                "pubdate": pubdate.isoformat() if pubdate is not None else "",
                "description": item.get("description") or "",
                "image": _first_image(item) or "",
                "unique_id": item.get("unique_id") or "",
            }
        )
    return buffer.getvalue()


def format_feed(feed, fmt="json", public_url=None):
    """Renders ``feed`` in the requested format.

    :param feed: internal feed dictionary.
    :param fmt: one of :data:`SUPPORTED_FORMATS`.
    :param public_url: canonical URL of the generated feed (used as ``rel=self``
        for RSS/Atom output).
    :returns: the serialized feed as a string.
    :raises ValueError: when ``fmt`` is not supported.
    """
    fmt = (fmt or "json").lower()
    if fmt == "json":
        return to_json(feed)
    if fmt == "rss":
        return to_rss(feed, public_url=public_url)
    if fmt == "atom":
        return to_atom(feed, public_url=public_url)
    if fmt == "csv":
        return to_csv(feed)
    raise ValueError(
        "Unsupported format '%s'. Supported formats: %s"
        % (fmt, ", ".join(SUPPORTED_FORMATS))
    )


# ---------------------------------------------------------------------------
# Scan results (list of discovered feeds)
# ---------------------------------------------------------------------------
#
# ``FeedsFinder.find_feeds`` returns a dictionary describing feeds discovered on
# a page (as opposed to individual news items)::
#
#     {
#         "url": str,
#         "items": [
#             {
#                 "title": str,
#                 "url": str,
#                 "feedtype": "rss" | "atom" | "html" | "undefined",
#                 "num_entries": int,        # optional
#                 "language": str,           # optional
#                 "confidence": float,       # optional
#             },
#             ...
#         ],
#     }


def _scan_feed_description(entry):
    parts = []
    if entry.get("feedtype"):
        parts.append("type: %s" % entry["feedtype"])
    if entry.get("num_entries") is not None:
        parts.append("entries: %s" % entry["num_entries"])
    if entry.get("language"):
        parts.append("language: %s" % entry["language"])
    if entry.get("confidence") is not None:
        parts.append("confidence: %s" % entry["confidence"])
    return "; ".join(parts) or None


def _scan_to_feed(results):
    """Maps discovered feeds onto the internal feed-dict shape.

    Each discovered feed becomes an item so it can be rendered as RSS/Atom.
    """
    source = results.get("url") or ""
    items = []
    for entry in results.get("items", []):
        link = entry.get("url")
        items.append(
            {
                "title": entry.get("title") or link or "(no title)",
                "description": _scan_feed_description(entry),
                "pubdate": None,
                "unique_id": link or entry.get("title"),
                "link": link,
                "extra": {"links": [link] if link else [], "images": []},
            }
        )
    return {
        "title": "Feeds found on %s" % source,
        "language": "en",
        "link": source,
        "description": "Feeds discovered on %s" % source,
        "items": items,
    }


def scan_to_csv(results):
    """Serializes discovered feeds to a CSV string."""
    buffer = io.StringIO()
    fieldnames = ["title", "url", "feedtype", "num_entries", "language", "confidence"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for entry in results.get("items", []):
        writer.writerow(
            {
                "title": entry.get("title") or "",
                "url": entry.get("url") or "",
                "feedtype": entry.get("feedtype") or "",
                "num_entries": entry.get("num_entries", ""),
                "language": entry.get("language") or "",
                "confidence": entry.get("confidence", ""),
            }
        )
    return buffer.getvalue()


def scan_to_opml(results):
    """Serializes discovered feeds to an OPML 2.0 subscription list."""
    source = results.get("url") or ""
    lines = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        '<opml version="2.0">',
        "  <head>",
        "    <title>%s</title>" % escape("Feeds found on %s" % source),
        "  </head>",
        "  <body>",
    ]
    for entry in results.get("items", []):
        title = entry.get("title") or entry.get("url") or ""
        xml_url = entry.get("url") or ""
        lines.append(
            "    <outline text=%s title=%s type=%s xmlUrl=%s/>"
            % (
                quoteattr(title),
                quoteattr(title),
                quoteattr("rss"),
                quoteattr(xml_url),
            )
        )
    lines.append("  </body>")
    lines.append("</opml>")
    return "\n".join(lines) + "\n"


def format_scan(results, fmt="json", public_url=None):
    """Renders ``scan`` results in the requested format.

    :param results: dictionary returned by ``FeedsFinder.find_feeds``.
    :param fmt: one of :data:`SCAN_FORMATS`.
    :param public_url: canonical URL of the generated feed (RSS/Atom ``rel=self``).
    :returns: the serialized results as a string.
    :raises ValueError: when ``fmt`` is not supported.
    """
    fmt = (fmt or "json").lower()
    if fmt == "json":
        return to_json(results)
    if fmt == "csv":
        return scan_to_csv(results)
    if fmt == "opml":
        return scan_to_opml(results)
    if fmt in ("rss", "atom"):
        feed = _scan_to_feed(results)
        return to_rss(feed, public_url=public_url) if fmt == "rss" else to_atom(
            feed, public_url=public_url
        )
    raise ValueError(
        "Unsupported format '%s'. Supported formats: %s"
        % (fmt, ", ".join(SCAN_FORMATS))
    )

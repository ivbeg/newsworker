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
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

import yaml

#: Supported output format identifiers for extracted feeds.
SUPPORTED_FORMATS = ("json", "rss", "atom", "csv", "jsonfeed", "html", "markdown", "yaml")

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


def _enclosure_length(item):
    """Returns a known enclosure byte length for ``item`` or ``None``.

    The length is only emitted when the extractor recorded a real value
    (``extra.enclosure_length``); otherwise it is omitted rather than reported
    as a misleading ``0``.
    """
    extra = item.get("extra") or {}
    length = extra.get("enclosure_length")
    try:
        return int(length) if length is not None else None
    except (TypeError, ValueError):
        return None


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
        if item.get("content"):
            entry.content(item["content"])
        if item.get("description"):
            entry.description(item["description"])
        if item_link:
            entry.link(href=item_link)
        if item.get("author"):
            entry.author(name=item["author"])
        if item.get("categories"):
            entry.category([{"term": c} for c in item["categories"]])
        pubdate = _ensure_tz(item.get("pubdate"))
        if pubdate is not None:
            entry.pubDate(pubdate)
            entry.updated(pubdate)
        image = _first_image(item)
        if image:
            length = _enclosure_length(item)
            entry.enclosure(image, str(length) if length is not None else "0", "image/jpeg")
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
    fieldnames = [
        "title",
        "link",
        "pubdate",
        "description",
        "image",
        "author",
        "categories",
        "unique_id",
    ]
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
                "author": item.get("author") or "",
                "categories": ", ".join(item.get("categories") or []),
                "unique_id": item.get("unique_id") or "",
            }
        )
    return buffer.getvalue()


def to_jsonfeed(feed, public_url=None):
    """Serializes ``feed`` to a JSON Feed 1.1 document.

    See https://jsonfeed.org/version/1.1. Reuses the internal feed dict without
    changing its shape.
    """
    out = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": feed.get("title") or "News feed",
        "home_page_url": feed.get("link"),
        "feed_url": public_url,
        "items": [],
    }
    if feed.get("language"):
        out["language"] = feed["language"]
    for item in feed.get("items", []):
        entry = {
            "id": item.get("unique_id") or item.get("link") or "",
            "title": item.get("title") or "(no title)",
        }
        if item.get("link"):
            entry["url"] = item["link"]
        if item.get("description"):
            entry["content_text"] = item["description"]
        pubdate = _ensure_tz(item.get("pubdate"))
        if pubdate is not None:
            entry["date_published"] = pubdate.isoformat()
        if item.get("author"):
            entry["authors"] = [{"name": item["author"]}]
        if item.get("categories"):
            entry["tags"] = list(item["categories"])
        image = _first_image(item)
        if image:
            entry["image"] = image
        out["items"].append(entry)
    return json.dumps(out, indent=2, ensure_ascii=False, default=_date_handler)


def _format_item_date(item):
    pubdate = item.get("pubdate")
    if pubdate is None:
        return ""
    try:
        return pubdate.isoformat()
    except AttributeError:
        return str(pubdate)


def to_html(feed):
    """Serializes ``feed`` to an HTML preview page rendering items as cards."""
    title = escape(feed.get("title") or "News feed")
    parts = [
        "<!DOCTYPE html>",
        '<html lang="%s">' % escape(feed.get("language") or "en"),
        "<head>",
        '<meta charset="utf-8">',
        "<title>%s</title>" % title,
        "<style>",
        "body{font-family:system-ui,sans-serif;max-width:48rem;margin:2rem auto;"
        "padding:0 1rem;line-height:1.5}",
        ".card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}",
        ".card h2{margin:0 0 .25rem;font-size:1.1rem}",
        ".card .date{color:#666;font-size:.85rem}",
        "</style>",
        "</head>",
        "<body>",
        "<h1>%s</h1>" % title,
    ]
    for item in feed.get("items", []):
        item_title = escape(item.get("title") or item.get("description") or "(no title)")
        link = item.get("link")
        date = escape(_format_item_date(item))
        parts.append('<article class="card">')
        if link:
            parts.append(
                '<h2><a href="%s">%s</a></h2>' % (escape(link), item_title)
            )
        else:
            parts.append("<h2>%s</h2>" % item_title)
        if date:
            parts.append('<div class="date">%s</div>' % date)
        if item.get("description"):
            parts.append("<p>%s</p>" % escape(item["description"]))
        parts.append("</article>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


def to_markdown(feed):
    """Serializes ``feed`` items to a Markdown bulleted list."""
    lines = ["# %s" % (feed.get("title") or "News feed"), ""]
    for item in feed.get("items", []):
        title = item.get("title") or item.get("description") or "(no title)"
        link = item.get("link")
        date = _format_item_date(item)
        heading = "[%s](%s)" % (title, link) if link else title
        prefix = "- **%s** — " % date if date else "- "
        lines.append("%s%s" % (prefix, heading))
    return "\n".join(lines) + "\n"


def to_yaml(feed):
    """Serializes ``feed`` to a YAML document (symmetric with the spec format)."""
    return yaml.safe_dump(feed, sort_keys=False, allow_unicode=True)


def read_opml(source):
    """Parses an OPML document into ``[{title, url, html_url}]`` entries.

    ``source`` may be a filesystem path or a string of OPML XML. Only outlines
    carrying an ``xmlUrl`` attribute (feed subscriptions) are returned.
    """
    import os

    if isinstance(source, str) and (
        "\n" in source or source.lstrip().startswith("<")
    ) and not os.path.exists(source):
        root = ET.fromstring(source)
    else:
        root = ET.parse(source).getroot()
    entries = []
    for outline in root.iter("outline"):
        xml_url = outline.get("xmlUrl")
        if not xml_url:
            continue
        entries.append(
            {
                "title": outline.get("text") or outline.get("title") or xml_url,
                "url": xml_url,
                "html_url": outline.get("htmlUrl"),
            }
        )
    return entries


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
    if fmt == "jsonfeed":
        return to_jsonfeed(feed, public_url=public_url)
    if fmt == "html":
        return to_html(feed)
    if fmt == "markdown":
        return to_markdown(feed)
    if fmt == "yaml":
        return to_yaml(feed)
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

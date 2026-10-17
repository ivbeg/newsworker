"""Model Context Protocol server: newsworker as tools for AI assistants.

``newsworker mcp`` speaks MCP over stdio (``pip install 'newsworker[mcp]'``).
Assistants get three tools: extract the latest news items from a page, find
the feeds a site publishes, and explain an extraction. Every fetch goes
through the same policy as the CLI (robots.txt, private-address blocking,
per-host pacing, size limits).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

#: Upper bound on items returned to a model in one call.
MAX_ITEMS = 100
_DESCRIPTION_CHARS = 500


def _item(item: dict[str, Any]) -> dict[str, Any]:
    pubdate = item.get("pubdate")
    description = item.get("description") or ""
    return {
        "title": item.get("title"),
        "link": item.get("link"),
        "published": pubdate.isoformat() if isinstance(pubdate, dt.datetime) else None,
        "description": description[:_DESCRIPTION_CHARS],
        "author": item.get("author"),
        "categories": item.get("categories") or [],
    }


def extract_news(service, url: str, limit: int = 20) -> dict[str, Any]:
    """Latest items of a news page or feed, newest first, as plain JSON data."""
    feed, diagnostics = service.get_feed_with_diagnostics(url)
    items = list(feed.get("items", []))
    items.sort(
        key=lambda item: item.get("pubdate").timestamp() if item.get("pubdate") else 0,
        reverse=True,
    )
    limit = max(1, min(int(limit), MAX_ITEMS))
    return {
        "source": url,
        "title": feed.get("title"),
        "language": feed.get("language"),
        "strategy": diagnostics.chosen_strategy if diagnostics else None,
        "confidence": diagnostics.confidence if diagnostics else None,
        "warnings": list(diagnostics.warnings) if diagnostics else [],
        "items": [_item(item) for item in items[:limit]],
    }


def find_feeds(settings, url: str) -> dict[str, Any]:
    """Feeds (RSS/Atom/JSON Feed) a page or site advertises, verified."""
    from .finder import FeedsFinder

    result = FeedsFinder(settings).find_feeds(url, noverify=False)
    return {
        "source": url,
        "error": result.get("error"),
        "feeds": [
            {
                key: feed.get(key)
                for key in ("title", "url", "feedtype", "num_entries", "language")
                if feed.get(key) is not None
            }
            for feed in result.get("items", [])
        ],
    }


def build_server(settings=None):
    """Create the FastMCP server; requires the ``mcp`` extra."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - exercised by the CLI message
        raise RuntimeError(
            "The MCP server needs the mcp extra: pip install 'newsworker[mcp]'"
        ) from exc

    from . import explain as explaining
    from .service import FeedService
    from .settings import Settings

    settings = settings or Settings.resolve(None)
    service = FeedService(settings=settings)
    # Tools only read public web pages; they never change anything.
    read_only = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
    server = FastMCP(
        "newsworker",
        instructions=(
            "Read news from websites, including sites without RSS. Use extract_news "
            "for the latest items of a page or feed, find_feeds to discover a site's "
            "feeds, and explain_page when extraction looks wrong."
        ),
    )

    @server.tool(name="extract_news", annotations=read_only)
    def extract_news_tool(url: str, limit: int = 20) -> dict[str, Any]:
        """Return the latest news items (title, link, published, description) of a
        news listing page or feed URL, newest first. ``limit`` caps the items (≤ 100)."""
        return extract_news(service, url, limit)

    @server.tool(name="find_feeds", annotations=read_only)
    def find_feeds_tool(url: str) -> dict[str, Any]:
        """Return the RSS/Atom/JSON feeds a web page advertises, with entry counts."""
        return find_feeds(settings, url)

    @server.tool(name="explain_page", annotations=read_only)
    def explain_page_tool(url: str) -> str:
        """Explain how newsworker extracts news from a page: date groups found,
        strategy chosen, resulting items and hints when the result looks wrong."""
        return explaining.to_text(explaining.explain(service, url))

    return server


def run(settings: Any | None = None) -> None:
    build_server(settings).run("stdio")

import asyncio
import datetime as dt
import sys

import pytest

from newsworker.mcp_server import MAX_ITEMS, extract_news

UTC = dt.timezone.utc


class _Diagnostics:
    chosen_strategy = "spec"
    confidence = 0.9
    warnings = []


class _Service:
    def get_feed_with_diagnostics(self, url):
        items = [
            {
                "title": f"Item {n}",
                "link": f"https://n.example/{n}",
                "description": "d" * 900,
                "pubdate": dt.datetime(2026, 10, n, tzinfo=UTC),
            }
            for n in (3, 9, 1)
        ] + [{"title": "Undated", "link": "https://n.example/u"}]
        return {"title": "News", "language": "en", "items": items}, _Diagnostics()


def test_extract_news_returns_newest_first_and_trims():
    result = extract_news(_Service(), "https://n.example/", limit=2)
    assert [item["title"] for item in result["items"]] == ["Item 9", "Item 3"]
    assert result["items"][0]["published"] == "2026-10-09T00:00:00+00:00"
    assert len(result["items"][0]["description"]) == 500
    assert result["strategy"] == "spec"
    assert len(extract_news(_Service(), "https://n.example/", limit=10_000)["items"]) <= MAX_ITEMS


def test_server_registers_read_only_tools(tmp_path):
    pytest.importorskip("mcp")
    from newsworker.mcp_server import build_server
    from newsworker.settings import Settings

    server = build_server(Settings(cache_dir=str(tmp_path)))
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == {"extract_news", "find_feeds", "explain_page"}
    assert all(tool.annotations.readOnlyHint for tool in tools.values())


def test_stdio_server_answers_an_mcp_client(tmp_path):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    config = tmp_path / "config.yaml"
    config.write_text(f"cache_dir: {tmp_path / 'cache'}\n")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "newsworker", "mcp", "-c", str(config)]
    )

    async def session():
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            return sorted(tool.name for tool in (await client.list_tools()).tools)

    names = asyncio.run(asyncio.wait_for(session(), timeout=60))
    assert names == ["explain_page", "extract_news", "find_feeds"]

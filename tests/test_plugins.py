"""Tests for extractor plugins, site bridges and async transport."""

import pytest

from newsworker.bridges import SiteBridge, load_bridge_file, select_bridge
from newsworker.plugins import BaseExtractorPlugin, select_plugin
from newsworker.service import FeedService
from newsworker.spec import FeedSpec, FieldRule, ItemsRule, SpecExtractor
from newsworker.async_fetch import aiohttp_available, fetch_urls_concurrent


class _EchoPlugin(BaseExtractorPlugin):
    def __init__(self, prefix="plugin"):
        self.prefix = prefix

    def matches(self, url):
        return "plugin.example" in url

    def extract(self, url, data=None, **kwargs):
        return {
            "title": self.prefix,
            "language": "en",
            "link": url,
            "description": self.prefix,
            "items": [{"title": "from-plugin", "unique_id": "p1", "link": url}],
        }


def test_select_plugin_first_match():
    plugins = [_EchoPlugin("a"), _EchoPlugin("b")]
    chosen = select_plugin("https://plugin.example/x", plugins)
    assert chosen is plugins[0]
    assert select_plugin("https://other.example/", plugins) is None


def test_plugin_extract_via_service():
    svc = FeedService(plugins=[_EchoPlugin()], bridges=[])
    feed = svc.get_feed("https://plugin.example/news", data=b"<html></html>")
    assert feed["title"] == "plugin"
    assert feed["items"][0]["title"] == "from-plugin"


def test_bridge_matches_host_and_path():
    spec = FeedSpec(
        title="Bridge",
        items=ItemsRule(selector="li.news-item"),
        fields={"title": FieldRule(selector="a", source="text")},
    )
    bridge = SiteBridge(host="example.com", path_pattern="/news*", spec=spec)
    assert bridge.matches("https://example.com/news")
    assert not bridge.matches("https://other.com/news")


def test_bridge_extraction(news_list_html, tmp_path):
    bridge_path = tmp_path / "test-bridge.yaml"
    bridge_path.write_text(
        """
match:
  host: example.com
  path: /news*
spec:
  version: 1
  feed:
    title: Example News Portal
    language: en
  items:
    selector: li.news-item
    selector_type: css
    container: /html/body/main/ul
  fields:
    date:
      selector: span.date
      source: text
      patterns: ["dt:date:date_9"]
      required: true
    title:
      selector: a
      source: text
    link:
      selector: a
      source: attr:href
      absolute: true
""",
        encoding="utf-8",
    )
    bridge = load_bridge_file(str(bridge_path))
    spec = select_bridge("https://example.com/news", [bridge])
    assert spec is not None
    feed = SpecExtractor().extract(
        "https://example.com/news", spec, data=news_list_html
    )
    assert len(feed["items"]) == 4


def test_service_uses_bridge(news_list_html):
    spec = FeedSpec(
        title="Example News Portal",
        language="en",
        items=ItemsRule(
            selector="li.news-item",
            selector_type="css",
            container="/html/body/main/ul",
        ),
        fields={
            "date": FieldRule(
                selector="span.date",
                source="text",
                patterns=["dt:date:date_9"],
                required=True,
            ),
            "title": FieldRule(selector="a", source="text"),
            "link": FieldRule(selector="a", source="attr:href", absolute=True),
        },
    )
    bridge = SiteBridge(host="example.com", path_pattern="/news*", spec=spec)
    svc = FeedService(plugins=[], bridges=[bridge])
    feed = svc.get_feed("https://example.com/news", data=news_list_html)
    assert len(feed["items"]) == 4


def test_async_unavailable_raises():
    if aiohttp_available():
        pytest.skip("aiohttp is installed")
    from newsworker.settings import Settings

    with pytest.raises(RuntimeError, match="aiohttp"):
        fetch_urls_concurrent(["https://example.com"], Settings())


def test_get_feeds_async_falls_back_without_aiohttp(monkeypatch):
    monkeypatch.setattr("newsworker.async_fetch.aiohttp_available", lambda: False)
    calls = {"sync": 0}
    original = FeedService.get_feeds

    def wrapper(self, urls, max_workers=4, force_refresh=False, use_async=None):
        if use_async is False:
            calls["sync"] += 1
            return {u: {"title": u, "items": []} for u in urls}
        return original(self, urls, max_workers, force_refresh, use_async)

    monkeypatch.setattr(FeedService, "get_feeds", wrapper)
    svc = FeedService(use_cache=False, plugins=[], bridges=[])
    svc.settings.use_async = True
    results = svc.get_feeds(["https://example.com/news"], use_async=True)
    assert calls["sync"] == 1
    assert "https://example.com/news" in results

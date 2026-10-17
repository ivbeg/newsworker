"""Regressions for stale specs, identities, caches, specs, URLs and watch delivery."""

import io
import json
import pathlib

import pytest
from typer.testing import CliRunner

from newsworker.cache import ContentCache, SpecCache
from newsworker.core import _run_watch_iteration, app
from newsworker.dedup import DedupStore
from newsworker.delivery import DeliveryPayload, StdoutChannel, deliver_webhook
from newsworker.formats import format_feed
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.sources import DocumentSource, DocumentSourceError
from newsworker.spec import FeedSpec, SpecValidationError, select_nodes, validate_spec_dict
from newsworker.tools import assign_item_identities, clean_url

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
NEWS_LIST = (FIXTURES / "news_list.html").read_bytes()
URL = "https://example.org/news"


def _service(tmp_path, **settings):
    values = {"cache_dir": str(tmp_path), "respect_robots": False}
    values.update(settings)
    return FeedService(Settings(**values))


# --- stale inferred specs ---------------------------------------------------


def test_obsolete_inferred_spec_is_rebuilt(tmp_path):
    service = _service(tmp_path)
    assert len(service.get_feed(URL, data=NEWS_LIST)["items"]) == 4
    spec = service.spec_cache.get(URL)
    spec.items.selector = "section.removed-layout"
    service.spec_cache.set(URL, spec)

    feed, diagnostics = service.get_feed_with_diagnostics(URL, data=NEWS_LIST)
    assert len(feed["items"]) == 4
    assert diagnostics.chosen_strategy == "rebuilt_spec"
    assert service.spec_cache.get(URL).items.selector != "section.removed-layout"


def test_explicit_empty_spec_is_not_replaced(tmp_path):
    service = _service(tmp_path)
    spec = FeedSpec.from_dict(
        {"items": {"selector": "section.nothing"}, "fields": {"title": {"selector": "a"}}}
    )
    feed = service.get_feed(URL, data=NEWS_LIST, explicit_spec=spec)
    assert feed["items"] == []


def test_local_documents_do_not_touch_the_live_spec_cache(tmp_path):
    service = _service(tmp_path)
    source = DocumentSource(kind="file", base_url=URL, location="x.html", data=NEWS_LIST)
    service.get_feed_source(source)
    assert service.spec_cache.get(URL) is None


# --- stable output ------------------------------------------------------------


def test_unchanged_page_renders_identical_bytes(tmp_path):
    service = _service(tmp_path)
    service.get_feed(URL, data=NEWS_LIST)
    for fmt in ("json", "rss", "atom", "jsonfeed"):
        first = format_feed(service.get_feed(URL, data=NEWS_LIST), fmt=fmt)
        second = format_feed(service.get_feed(URL, data=NEWS_LIST), fmt=fmt)
        assert first == second, fmt


def test_item_identity_follows_the_link_not_the_teaser():
    items = [
        {"unique_id": "h1", "link": "https://a.example/1", "description": "old"},
        {"unique_id": "h2", "link": "https://a.example/2"},
    ]
    assign_item_identities(items, page_url="https://a.example/")
    edited = [{"unique_id": "h9", "link": "https://a.example/1", "description": "new"}]
    assign_item_identities(edited, page_url="https://a.example/")
    assert edited[0]["unique_id"] == items[0]["unique_id"]
    assert items[0]["content_hash"] == "h1"


def test_items_sharing_the_page_link_keep_content_ids():
    items = [
        {"unique_id": "h1", "link": "https://a.example/"},
        {"unique_id": "h2", "link": "https://a.example/"},
    ]
    assign_item_identities(items, page_url="https://a.example/")
    assert [item["unique_id"] for item in items] == ["h1", "h2"]


# --- spec schema matches execution ------------------------------------------


def test_class_only_css_selector_is_css():
    validate_spec_dict({"items": {"selector": ".news-card", "selector_type": "css"}})
    from lxml.html import fromstring

    document = fromstring("<div><p class='news-card'>a</p><p>b</p></div>")
    assert [node.text for node in select_nodes(document, ".news-card")] == ["a"]
    assert [node.text for node in select_nodes(document, "./p[2]")] == ["b"]


def test_href_source_alias_reads_the_attribute(tmp_path):
    html = b"""<html><body><ul>
      <li><span>16.10.2026</span><a href='/one'>First headline text here</a></li>
      <li><span>15.10.2026</span><a href='/two'>Second headline text here</a></li>
    </ul></body></html>"""
    spec = FeedSpec.from_dict(
        {
            "items": {"selector": "li"},
            "fields": {
                "date": {"selector": "span", "source": "text", "required": True},
                "title": {"selector": "a", "source": "text"},
                "link": {"selector": "a", "source": "href", "absolute": True},
            },
        }
    )
    feed = _service(tmp_path).get_feed(URL, data=html, explicit_spec=spec)
    assert [item["link"] for item in feed["items"]] == [
        "https://example.org/one",
        "https://example.org/two",
    ]


def test_invalid_patterns_are_rejected():
    with pytest.raises(SpecValidationError):
        validate_spec_dict({"fields": {"date": {"selector": "span", "patterns": "dt:date"}}})


def test_explicit_language_overrides_spec_language(tmp_path):
    spec = FeedSpec.from_dict(
        {"language": "en", "items": {"selector": "li"}, "fields": {"title": {"selector": "a"}}}
    )
    html = b"<html><body><ul><li><a href='/a'>Headline</a></li></ul></body></html>"
    feed = _service(tmp_path, default_language="ru").get_feed(URL, data=html, explicit_spec=spec)
    assert feed["language"] == "ru"


# --- URLs and caches ------------------------------------------------------------


def test_clean_url_preserves_encoding_repeats_and_fragment():
    url = "https://ex.com/a?id=a%26b&tag=one&tag=two&utm_source=x&fbclid=y&e=#frag"
    assert clean_url(url) == "https://ex.com/a?id=a%26b&tag=one&tag=two&e=#frag"


def test_corrupt_cache_metadata_is_a_miss(tmp_path):
    cache = ContentCache(str(tmp_path), ttl=3600)
    cache.set(URL, b"<html></html>", meta={"etag": '"1"'})
    pathlib.Path(cache._meta_path(URL)).write_text("{broken")
    assert cache.get_generation(URL) == (None, {})


def test_corrupt_cached_spec_is_a_miss(tmp_path):
    cache = SpecCache(str(tmp_path))
    pathlib.Path(cache.path_for(URL)).parent.mkdir(parents=True)
    pathlib.Path(cache.path_for(URL)).write_text("items: [unclosed")
    assert cache.get(URL) is None


def test_revalidation_stores_fresh_validators(tmp_path):
    service = _service(tmp_path)
    calls = []

    def fake_fetch(url, user_agent=None, conditional=None, context=None, max_bytes=None):
        calls.append(dict(conditional or {}))
        active = service.extractor._context()
        if not calls[:-1]:
            active.response_meta = {"etag": '"v1"', "status": 200}
            return NEWS_LIST
        active.response_meta = {"etag": f'"v{len(calls)}"', "status": 304}
        return None

    service.extractor.fetch = fake_fetch
    for _ in range(3):
        service.get_feed(URL, revalidate=True)
    assert calls[1]["etag"] == '"v1"'
    assert calls[2]["etag"] == '"v2"'


def test_local_input_is_bounded():
    with pytest.raises(DocumentSourceError):
        DocumentSource.stdin(base_url=URL, stream=io.BytesIO(b"x" * 11), max_bytes=10)


# --- watch and delivery -----------------------------------------------------------


class _FailingService:
    settings = Settings()

    def get_feed(self, url, **kwargs):
        raise ConnectionError("source down")


class _Recorder:
    name = "recorder"
    destination_identity = "recorder"

    def __init__(self):
        self.sent = []

    def validate_config(self):
        return None

    def send(self, payload):
        from newsworker.delivery import DeliveryResult

        self.sent.append(payload)
        return DeliveryResult("success")


def test_pending_deliveries_drain_while_the_source_is_down(tmp_path):
    store = DedupStore(str(tmp_path / "outbox.sqlite3"))
    channel = _Recorder()
    store.enqueue(
        URL,
        [{"title": "queued", "unique_id": "1", "pubdate": None}],
        channel=channel.name,
        destination=channel.destination_identity,
        feed_meta={"title": "Feed", "link": URL},
    )
    result = _run_watch_iteration(
        _FailingService(), URL, "json", store, None, 1, channels=[channel]
    )
    assert [payload.item["title"] for payload in channel.sent] == ["queued"]
    assert channel.sent[0].feed["title"] == "Feed"
    assert result.status["fetch_error"].startswith("ConnectionError")
    assert not result.successful
    store.close()


def test_late_failure_cannot_undo_a_newer_delivery(tmp_path):
    clock = {"now": 1000.0}
    store = DedupStore(str(tmp_path / "outbox.sqlite3"), clock=lambda: clock["now"])
    store.enqueue(URL, [{"title": "a", "unique_id": "1"}], channel="c", destination="d")
    first = store.claim_due(lease_seconds=10)[0]
    clock["now"] += 20
    store.release_expired_claims()
    second = store.claim_due(lease_seconds=10)[0]
    assert store.acknowledge(second.idempotency_key, second.claim_token)
    assert not store.fail(first.idempotency_key, "late", token=first.claim_token)
    assert store.counts() == {"delivered": 1}
    store.close()


def test_watch_stdout_honours_the_format(tmp_path):
    stream = io.StringIO()
    channel = StdoutChannel(stream=stream, fmt="rss")
    payloads = [
        DeliveryPayload(
            {
                "title": "One",
                "link": "https://a.example/1",
                "unique_id": "1",
                "pubdate": "2026-10-16T10:00:00+00:00",
            },
            {"title": "Feed", "link": URL},
            "k1",
        )
    ]
    assert all(result.successful for result in channel.send_batch(payloads))
    assert stream.getvalue().lstrip().startswith("<?xml")
    assert "<title>One</title>" in stream.getvalue()


def test_webhook_helper_uses_distinct_item_keys():
    class Session:
        def __init__(self):
            self.keys = []

        def request(self, method, url, **kwargs):
            self.keys.append(kwargs["headers"]["Idempotency-Key"])
            return _Response()

    class _Response:
        status_code = 200
        headers = {}

        def iter_content(self, chunk_size):
            return iter([b"{}"])

        def close(self):
            return None

    session = Session()
    from newsworker.fetch import FetchPolicy

    assert deliver_webhook(
        "https://hooks.example/x",
        [{"title": "a"}, {"title": "b"}],
        session=session,
        policy=FetchPolicy(block_private_hosts=False),
    )
    assert len(set(session.keys)) == 2


def test_one_shot_watch_with_failing_source_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr("newsworker.core.FeedService", lambda settings: _FailingService())
    config = tmp_path / "config.yaml"
    config.write_text(json.dumps({"cache_dir": str(tmp_path)}))
    result = CliRunner().invoke(app, ["watch", URL, "--max-iterations", "1", "-c", str(config)])
    assert result.exit_code == 1
    assert "could not fetch" in result.output


def test_scan_of_unreachable_source_fails(monkeypatch):
    from newsworker.finder import FeedsFinder

    def boom(self, url):
        raise ConnectionError("unreachable")

    monkeypatch.setattr(FeedsFinder, "_fetch", boom)
    result = CliRunner().invoke(app, ["scan", "https://down.example/"])
    assert result.exit_code == 1


def test_extract_fail_on_empty(tmp_path):
    page = tmp_path / "empty.html"
    page.write_text("<html><body><p>No news here</p></body></html>")
    config = tmp_path / "config.yaml"
    config.write_text(json.dumps({"cache_dir": str(tmp_path / "cache")}))
    args = ["extract", "--file", str(page), "--base-url", URL, "-c", str(config)]
    assert CliRunner().invoke(app, args).exit_code == 0
    assert CliRunner().invoke(app, args + ["--fail-on-empty"]).exit_code == 3


def test_user_bridge_overrides_bundled_and_hosts_list(tmp_path):
    from newsworker.bridges import load_bridges, select_bridge

    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    (bundled / "a.yaml").write_text(
        "match: {host: news.example}\nspec: {items: {selector: li.bundled}}\n"
    )
    (user / "a.yaml").write_text(
        "match: {hosts: [news.example, mirror.example]}\nspec: {items: {selector: li.user}}\n"
    )
    bridges = load_bridges(str(bundled), str(user))
    assert select_bridge("https://news.example/x", bridges).items.selector == "li.user"
    assert select_bridge("https://mirror.example/x", bridges).items.selector == "li.user"


ARTICLES = b"""<html lang='en'><head><title>T</title></head><body>
<article><time datetime='2026-08-04T10:00:00Z'>d</time><a href='/one'>First headline is long</a></article>
<article><time datetime='2026-08-03T10:00:00Z'>d</time><a href='/two'>Second headline is long</a></article>
<a rel='next' href='/page2'>Next</a>
</body></html>"""


def _article_spec():
    return FeedSpec.from_dict(
        {
            "items": {"selector": "article"},
            "fields": {
                "date": {"selector": "time", "source": "attr:datetime", "required": True},
                "title": {"selector": "a"},
                "link": {"selector": "a", "source": "href", "absolute": True},
            },
        }
    )


def test_pagination_merges_overlapping_pages_once(tmp_path):
    service = _service(tmp_path)
    second = ARTICLES.replace(b"/one", b"/three").replace(b"/page2", b"/page3")

    def fake_fetch(url, user_agent=None, conditional=None, context=None, max_bytes=None):
        return second

    service.extractor.fetch = fake_fetch
    feed = service.get_feed(URL, data=ARTICLES, explicit_spec=_article_spec(), max_pages=2)
    links = [item["link"] for item in feed["items"]]
    assert links == [
        "https://example.org/one",
        "https://example.org/two",
        "https://example.org/three",
    ]


def test_pagination_failure_is_reported(tmp_path):
    service = _service(tmp_path)

    def failing_fetch(url, user_agent=None, conditional=None, context=None, max_bytes=None):
        raise ConnectionError("page 2 down")

    service.extractor.fetch = failing_fetch
    feed, diagnostics = service.get_feed_with_diagnostics(
        URL, data=ARTICLES, explicit_spec=_article_spec(), max_pages=3
    )
    assert len(feed["items"]) == 2
    assert any("Pagination stopped" in warning for warning in diagnostics.warnings)


def test_full_text_failures_are_reported(tmp_path, monkeypatch):
    service = _service(tmp_path, full_text=True)

    def failing_fetch(url, user_agent=None, conditional=None, context=None, max_bytes=None):
        raise ConnectionError("article down")

    service.extractor.fetch = failing_fetch
    feed = service.get_feed(URL, data=ARTICLES, explicit_spec=_article_spec())
    assert "Full text unavailable for 2 of 2 item(s)" in feed["provenance"]["warnings"]


def test_readability_fallback_is_labelled_html(monkeypatch):
    import sys
    import types

    from newsworker.enrich import extract_fulltext_with_kind

    monkeypatch.setitem(sys.modules, "trafilatura", None)
    module = types.SimpleNamespace(
        Document=lambda payload: types.SimpleNamespace(summary=lambda: "<p>body</p>")
    )
    monkeypatch.setitem(sys.modules, "readability", module)
    assert extract_fulltext_with_kind(b"<html></html>") == ("<p>body</p>", "html")


def test_batch_manifest_reports_runtime_facts(tmp_path):
    from newsworker.core import app as cli_app

    pages = tmp_path / "urls.txt"
    pages.write_text(URL + "\n" + URL + "\n")
    config = tmp_path / "config.yaml"
    config.write_text(json.dumps({"cache_dir": str(tmp_path / "cache")}))

    class Service:
        def __init__(self, settings, use_cache=True):
            self.settings = settings

        def get_feeds(self, urls, max_workers=4, runtime=None):
            runtime[urls[0]] = {"elapsed_ms": 12.5, "cache_state": "miss", "transport": "thread"}
            return {urls[0]: {"title": "T", "items": [], "provenance": {"strategy": "spec"}}}

    import newsworker.core as core

    original = core.FeedService
    core.FeedService = Service
    try:
        manifest = tmp_path / "manifest.json"
        result = CliRunner().invoke(
            cli_app,
            [
                "batch",
                "--urls-file",
                str(pages),
                "-d",
                str(tmp_path / "out"),
                "--manifest",
                str(manifest),
                "-c",
                str(config),
            ],
        )
    finally:
        core.FeedService = original
    assert result.exit_code == 0, result.output
    records = json.loads(manifest.read_text())
    records = records.get("results", records) if isinstance(records, dict) else records
    assert len(records) == 1
    assert records[0]["elapsed_ms"] == 12.5 and records[0]["cache_state"] == "miss"

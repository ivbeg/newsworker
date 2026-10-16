import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from newsworker.jsrender import RenderResult
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.sources import DocumentSource
from newsworker.spec import FeedSpec, FieldRule, ItemsRule


def service(tmp_path, **overrides):
    settings = Settings(
        cache_dir=str(tmp_path),
        respect_robots=False,
        block_private_hosts=False,
        **overrides,
    )
    return FeedService(settings=settings)


def simple_spec():
    return FeedSpec(
        title="T",
        items=ItemsRule(selector="article", selector_type="css"),
        fields={
            "date": FieldRule(selector="time", source="attr:datetime", required=True),
            "title": FieldRule(selector="a", source="text"),
            "link": FieldRule(selector="a", source="attr:href", absolute=True),
        },
    )


HTML = b"""<html lang='en'><head><title>T</title></head><body>
<article><time datetime='2026-08-04T10:00:00Z'>date</time><a href='/one'>First headline is long</a></article>
<article><time datetime='2026-08-03T10:00:00Z'>date</time><a href='/two'>Second headline is long</a></article>
</body></html>"""


def test_service_explicit_spec_diagnostics_and_local_source(tmp_path):
    svc = service(tmp_path)
    context = svc.new_context(source="file", base_url="https://example.com/archive")
    feed = svc.get_feed(
        "https://example.com/archive", data=HTML, explicit_spec=simple_spec(), context=context
    )
    assert len(feed["items"]) == 2
    assert feed["items"][0]["pubdate"].tzinfo == datetime.timezone.utc
    assert context.diagnostics.chosen_strategy == "explicit_spec"
    source = DocumentSource(kind="file", base_url="https://example.com/archive", data=HTML)
    assert (
        svc.get_feed_source(source, explicit_spec=simple_spec())["provenance"]["source"] == "file"
    )


def test_service_plugin_and_extension_preservation(tmp_path):
    class Plugin:
        def matches(self, url):
            return url.endswith("/plugin")

        def extract(self, url, data=None, **kwargs):
            return {
                "title": "Plugin",
                "link": url,
                "description": "P",
                "language": "en",
                "items": [],
            }

    svc = FeedService(
        Settings(cache_dir=str(tmp_path), respect_robots=False, block_private_hosts=False),
        plugins=[Plugin()],
        bridges=[],
    )
    feed, diagnostics = svc.get_feed_with_diagnostics(
        "https://example.com/plugin", data=b"<html></html>"
    )
    assert feed["title"] == "Plugin" and diagnostics.chosen_strategy == "plugin"
    worker = svc._worker_service()
    assert any(isinstance(plugin, Plugin) for plugin in worker.plugins)


def test_service_content_cache_hit_revalidation_and_changed(tmp_path):
    svc = service(tmp_path, content_ttl=3600)
    calls = []
    payloads = [b"one", None, b"two"]

    def fake_fetch(url, user_agent=None, conditional=None, max_bytes=None):
        calls.append(conditional)
        svc.extractor.last_response_meta = {
            "etag": '"v1"' if len(calls) < 3 else '"v2"',
            "effective_url": url,
            "status": 200,
        }
        return payloads.pop(0)

    svc.extractor.fetch = fake_fetch
    url = "https://example.com/cache"
    context = svc.new_context(base_url=url)
    assert svc._fetch(url, context=context) == b"one"
    assert svc._fetch(url, context=svc.new_context(base_url=url)) == b"one"
    assert len(calls) == 1
    assert svc._fetch(url, revalidate=True, context=svc.new_context(base_url=url)) == b"one"
    assert calls[-1]["etag"] == '"v1"'
    assert svc._fetch(url, revalidate=True, context=svc.new_context(base_url=url)) == b"two"
    assert svc.content_cache.get(url) == b"two"


def test_service_spec_singleflight_cache_and_force_refresh(tmp_path, monkeypatch):
    svc = service(tmp_path)
    built = []

    def analyze(self, url, data=None, user_agent=None, require_items=False):
        built.append(url)
        return simple_spec()

    monkeypatch.setattr("newsworker.service.SpecAnalyzer.analyze", analyze)
    context = svc.new_context(base_url="https://example.com")
    first = svc._get_or_build_spec("https://example.com", HTML, context)
    second = svc._get_or_build_spec("https://example.com", HTML, context)
    assert first.fields and second.fields and built == ["https://example.com"]


def test_service_pagination_and_fulltext(tmp_path, monkeypatch):
    svc = service(tmp_path, full_text=True, full_text_workers=2)
    first = HTML.replace(b"</body>", b"<a rel='next' href='/page2'>Next</a></body>")

    def fake_fetch(url, user_agent=None, conditional=None, context=None, max_bytes=None):
        if url.endswith("page2"):
            return HTML.replace(b"/one", b"/three").replace(b"/two", b"/four")
        return b"<html><body><article>Full body text for the story.</article></body></html>"

    svc.extractor.fetch = fake_fetch
    monkeypatch.setattr(
        "newsworker.service.extract_fulltext_with_kind",
        lambda html, url=None: ("full text", "text"),
    )
    feed = svc.get_feed(
        "https://example.com/page1", data=first, explicit_spec=simple_spec(), max_pages=2
    )
    assert len(feed["items"]) == 4
    assert all(
        item["content"] == "full text" and item["content_kind"] == "text" for item in feed["items"]
    )


def test_service_undated_and_browser_paths(tmp_path, monkeypatch):
    cards = "".join(
        f"<article class='news-card'><h2><a href='/s/{i}'>Long news headline {i}</a></h2><p>Summary text {i}</p></article>"
        for i in range(4)
    ).encode()
    svc = service(tmp_path, undated_fallback=True)
    feed, diagnostics = svc.get_feed_with_diagnostics(
        "https://example.com/u", data=b"<html><body>" + cards + b"</body></html>"
    )
    assert len(feed["items"]) == 4 and diagnostics.chosen_strategy == "undated"

    rendered = HTML
    monkeypatch.setattr(
        "newsworker.jsrender.PlaywrightRenderer.render",
        lambda self, url: RenderResult(rendered, url, 4.2),
    )
    browser = service(tmp_path / "browser", render=True)
    feed, diagnostics = browser.get_feed_with_diagnostics(
        "https://example.com/render", explicit_spec=simple_spec()
    )
    assert len(feed["items"]) == 2
    assert diagnostics.metadata["rendered"] is True


def test_service_threaded_batch_success_failure_order(tmp_path, monkeypatch):
    svc = service(tmp_path)

    def get_feed(self, url, **kwargs):
        if "bad" in url:
            raise RuntimeError("bad source")
        return {"title": url, "items": []}

    monkeypatch.setattr(FeedService, "get_feed", get_feed)
    urls = ["https://example.com/a", "https://example.com/bad", "https://example.com/a"]
    results = svc.get_feeds(urls, max_workers=2)
    assert list(results) == urls[:2]
    assert results[urls[0]]["title"] == urls[0]
    assert results[urls[1]]["error_type"] == "RuntimeError"


def test_service_async_unavailable_falls_back(tmp_path, monkeypatch):
    svc = service(tmp_path, use_async=True)
    monkeypatch.setattr("newsworker.async_fetch.aiohttp_available", lambda: False)
    monkeypatch.setattr(
        FeedService,
        "get_feed",
        lambda self, url, **kwargs: {"title": url, "items": []},
    )
    result = svc.get_feeds(["https://example.com/a"], use_async=True)
    assert result["https://example.com/a"]["title"].endswith("/a")


def test_service_singleflight_same_url_and_mixed_url_isolation(tmp_path):
    svc = service(tmp_path)
    lock = threading.Lock()
    calls = []

    def fake_fetch(url, user_agent=None, conditional=None, context=None, max_bytes=None):
        with lock:
            calls.append(url)
        time.sleep(0.03)
        svc.extractor.last_response_meta = {
            "effective_url": url,
            "status": 200,
            "etag": f'"{url.rsplit("/", 1)[-1]}"',
        }
        return url.encode()

    svc.extractor.fetch = fake_fetch
    barrier = threading.Barrier(6)

    def same_worker():
        barrier.wait()
        return svc._fetch(
            "https://example.com/shared",
            context=svc.new_context(base_url="https://example.com/shared"),
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(same_worker) for _ in range(5)]
        barrier.wait()
        assert [future.result() for future in futures] == [b"https://example.com/shared"] * 5
    assert calls == ["https://example.com/shared"]

    barrier = threading.Barrier(3)

    def mixed_worker(url):
        barrier.wait()
        context = svc.new_context(base_url=url)
        body = svc._fetch(url, context=context)
        return body, context.response_meta["etag"]

    urls = ["https://example.com/alpha", "https://example.com/beta"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(mixed_worker, url) for url in urls]
        barrier.wait()
        results = [future.result() for future in futures]
    assert results == [
        (b"https://example.com/alpha", '"alpha"'),
        (b"https://example.com/beta", '"beta"'),
    ]


def test_shared_service_keeps_concurrent_languages_and_validators_isolated(tmp_path):
    svc = service(tmp_path)
    barrier = threading.Barrier(3)

    def build(language):
        url = f"https://example.com/{language}"
        context = svc.new_context(base_url=url)
        context.response_meta = {
            "etag": f'"{language}"',
            "effective_url": url,
            "status": 200,
        }
        localized = HTML.replace(b"lang='en'", f"lang='{language}'".encode())
        barrier.wait()
        feed = svc.get_feed(url, data=localized, explicit_spec=simple_spec(), context=context)
        return feed["language"], context.response_meta["etag"], feed["provenance"]["effective_url"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(build, language) for language in ("fr", "de")]
        barrier.wait()
        results = [future.result() for future in futures]
    assert results == [
        ("fr", '"fr"', "https://example.com/fr"),
        ("de", '"de"', "https://example.com/de"),
    ]

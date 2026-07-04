from newsworker.service import FeedService
from newsworker.settings import Settings


class _FakeService:
    """Stand-in worker service that fakes get_feed without any network/parsing."""

    def __init__(self, fail_for=None):
        self.fail_for = set(fail_for or [])

    def get_feed(self, url, force_refresh=False, explicit_spec=None):
        if url in self.fail_for:
            raise RuntimeError("boom for %s" % url)
        return {"title": url, "link": url, "items": [{"title": url}]}


def _service_with_fake_workers(monkeypatch, tmp_path, fail_for=None):
    settings = Settings(cache_dir=str(tmp_path))
    # Avoid constructing a real FeedExtractor (which loads date patterns).
    monkeypatch.setattr(FeedService, "__init__", lambda self: None)
    svc = FeedService()
    svc.settings = settings
    svc.use_cache = False
    monkeypatch.setattr(
        FeedService, "_worker_service", lambda self: _FakeService(fail_for)
    )
    return svc


def test_get_feeds_returns_feed_per_url(monkeypatch, tmp_path):
    svc = _service_with_fake_workers(monkeypatch, tmp_path)
    urls = ["https://a.example/x", "https://b.example/y", "https://c.example/z"]
    results = svc.get_feeds(urls, max_workers=3)
    assert set(results) == set(urls)
    for url in urls:
        assert results[url]["title"] == url


def test_get_feeds_deduplicates(monkeypatch, tmp_path):
    svc = _service_with_fake_workers(monkeypatch, tmp_path)
    results = svc.get_feeds(
        ["https://a.example/x", "https://a.example/x"], max_workers=2
    )
    assert len(results) == 1


def test_get_feeds_isolates_failures(monkeypatch, tmp_path):
    bad = "https://bad.example/x"
    svc = _service_with_fake_workers(monkeypatch, tmp_path, fail_for=[bad])
    results = svc.get_feeds(["https://ok.example/y", bad], max_workers=2)
    assert results["https://ok.example/y"]["items"]
    assert "error" in results[bad]


def test_get_feeds_empty():
    svc = FeedService.__new__(FeedService)
    assert svc.get_feeds([]) == {}

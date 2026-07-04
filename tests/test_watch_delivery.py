"""Tests for dedup, webhook delivery, pagination link detection and watch tick."""

from lxml.html import fromstring

from newsworker.core import _run_watch_iteration
from newsworker.dedup import DedupStore
from newsworker.delivery import deliver_webhook
from newsworker.tools import find_next_link


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_dedup_filters_seen_across_runs(tmp_path):
    store = DedupStore(str(tmp_path / "seen.sqlite3"))
    items = [{"unique_id": "1"}, {"unique_id": "2"}]
    new = store.filter_new("https://feed", items)
    assert len(new) == 2
    # Second run: same items are no longer new.
    again = store.filter_new("https://feed", items)
    assert again == []
    # A genuinely new item is returned.
    more = store.filter_new("https://feed", items + [{"unique_id": "3"}])
    assert [i["unique_id"] for i in more] == ["3"]
    store.close()


def test_dedup_scoped_per_feed(tmp_path):
    store = DedupStore(str(tmp_path / "seen.sqlite3"))
    store.filter_new("https://a", [{"unique_id": "x"}])
    # Same id under a different feed URL is still new.
    assert store.filter_new("https://b", [{"unique_id": "x"}])
    store.close()


def test_dedup_persists_across_instances(tmp_path):
    path = str(tmp_path / "seen.sqlite3")
    s1 = DedupStore(path)
    s1.filter_new("https://feed", [{"unique_id": "1"}])
    s1.close()
    s2 = DedupStore(path)
    assert s2.filter_new("https://feed", [{"unique_id": "1"}]) == []
    s2.close()


# ---------------------------------------------------------------------------
# Webhook delivery
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "headers": headers})

        class _Resp:
            status_code = self.statuses.pop(0)

        return _Resp()


def test_webhook_posts_json_payload():
    session = _FakeSession([200])
    ok = deliver_webhook(
        "https://hook.example/x",
        [{"title": "a", "unique_id": "1"}],
        feed={"title": "T", "link": "https://e"},
        session=session,
    )
    assert ok is True
    assert len(session.calls) == 1
    assert session.calls[0]["headers"]["Content-Type"] == "application/json"
    assert b'"items"' in session.calls[0]["data"]


def test_webhook_retries_then_succeeds():
    session = _FakeSession([500, 200])
    ok = deliver_webhook(
        "https://hook.example/x",
        [{"title": "a"}],
        retries=3,
        backoff=0,
        session=session,
    )
    assert ok is True
    assert len(session.calls) == 2


def test_webhook_gives_up_after_retries():
    session = _FakeSession([500, 500, 500])
    ok = deliver_webhook(
        "https://hook.example/x", [{"title": "a"}], retries=3, backoff=0, session=session
    )
    assert ok is False
    assert len(session.calls) == 3


def test_webhook_rejects_bad_url():
    import pytest

    with pytest.raises(ValueError):
        deliver_webhook("file:///etc/passwd", [{"title": "a"}])


# ---------------------------------------------------------------------------
# Pagination link detection
# ---------------------------------------------------------------------------


def test_find_next_link_rel_next():
    doc = fromstring(
        '<html><body><a rel="next" href="/page/2">Next</a></body></html>'
    )
    assert find_next_link(doc, "https://e.com/page/1") == "https://e.com/page/2"


def test_find_next_link_by_text():
    doc = fromstring('<html><body><a href="/older">Older posts</a></body></html>')
    assert find_next_link(doc, "https://e.com/") == "https://e.com/older"


def test_find_next_link_none():
    doc = fromstring("<html><body><a href='/x'>Home</a></body></html>")
    assert find_next_link(doc, "https://e.com/") is None


# ---------------------------------------------------------------------------
# Watch iteration
# ---------------------------------------------------------------------------


class _FakeService:
    def __init__(self, feed):
        self._feed = feed
        self.calls = 0

    def get_feed(self, url, max_pages=1):
        self.calls += 1
        return self._feed


def test_watch_iteration_emits_only_new(tmp_path, capsys):
    feed = {
        "title": "T",
        "link": "https://e.com",
        "language": "en",
        "description": "T",
        "items": [{"title": "a", "unique_id": "1"}, {"title": "b", "unique_id": "2"}],
    }
    svc = _FakeService(feed)
    dedup = DedupStore(str(tmp_path / "seen.sqlite3"))

    first = _run_watch_iteration(svc, "https://e.com", "json", dedup, None, 1)
    assert len(first) == 2
    # Second tick: nothing new, nothing emitted.
    second = _run_watch_iteration(svc, "https://e.com", "json", dedup, None, 1)
    assert second == []
    dedup.close()

"""Tests for dedup, webhook delivery, pagination link detection and watch tick."""

from lxml.html import fromstring
from typer.testing import CliRunner

from newsworker.core import WatchIterationResult, _run_watch_iteration, app
from newsworker.dedup import DedupStore
from newsworker.delivery import ChannelCapabilities, DeliveryResult, WebhookChannel, deliver_webhook
from newsworker.fetch import FetchPolicy
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


def test_legacy_seen_rows_migrate_without_redelivery(tmp_path):
    path = str(tmp_path / "seen.sqlite3")
    store = DedupStore(path)
    item = {"unique_id": "legacy"}
    assert store.filter_new("https://feed", [item]) == [item]
    assert (
        store.enqueue("https://feed", [item], channel="webhook", destination="webhook:opaque") == []
    )
    assert store.counts(channel="webhook") == {"delivered": 1}
    store.close()


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
    doc = fromstring('<html><body><a rel="next" href="/page/2">Next</a></body></html>')
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


def test_watch_tracks_multiple_destinations_independently(tmp_path):
    feed = {
        "title": "T",
        "link": "https://e.com",
        "items": [{"title": "a", "unique_id": "1"}],
    }

    class Channel:
        capabilities = ChannelCapabilities()

        def __init__(self, name, destination, results):
            self.name = name
            self.destination_identity = destination
            self.results = list(results)

        def validate_config(self):
            return None

        def send(self, payload):
            return self.results.pop(0)

    accepted = Channel("smtp", "smtp:a@example.com", [DeliveryResult("success")])
    deferred = Channel("telegram", "telegram:7", [DeliveryResult("retryable", "busy")])
    store = DedupStore(str(tmp_path / "outbox.sqlite3"))
    result = _run_watch_iteration(
        _FakeService(feed),
        "https://e.com",
        "json",
        store,
        None,
        1,
        channels=[accepted, deferred],
    )
    assert result.status == {
        "discovered": 1,
        "delivered": 1,
        "retried": 1,
        "failed": 1,
        "pending": 1,
        "terminal": 0,
        "fetch_error": None,
    }
    assert store.counts(channel="smtp") == {"delivered": 1}
    assert store.counts(channel="telegram") == {"retry": 1}
    store.close()


def test_webhook_destination_identity_does_not_persist_secret():
    channel = WebhookChannel(
        "https://hooks.example/send?token=secret",
        policy=FetchPolicy(block_private_hosts=False),
    )
    assert "secret" not in channel.destination_identity


def test_watch_one_shot_delivery_failure_exits_unsuccessfully(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(f"cache_dir: {tmp_path / 'cache'}\nrespect_robots: false\n")
    monkeypatch.setattr(
        "newsworker.core._run_watch_iteration",
        lambda *args, **kwargs: WatchIterationResult([], failed=1, pending=1),
    )
    result = CliRunner().invoke(
        app,
        [
            "watch",
            "https://example.com/news",
            "--max-iterations",
            "1",
            "--config",
            str(config),
        ],
    )
    assert result.exit_code == 1
    assert "pending delivery" in result.output

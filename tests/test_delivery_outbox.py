"""Delivery outbox lifecycle and the built-in delivery channels."""

import io

import pytest
from http_fakes import FakeResponse, FakeSession

from newsworker.dedup import DedupStore
from newsworker.delivery import (
    DeliveryPayload,
    DeliveryRegistry,
    SMTPChannel,
    StdoutChannel,
    TelegramChannel,
    WebhookChannel,
    default_registry,
    deliver_webhook,
)
from newsworker.fetch import (
    FetchPolicy,
    FetchResult,
)


def test_outbox_lifecycle_destination_scope_and_prune(tmp_path):
    now = [1000.0]
    store = DedupStore(str(tmp_path / "outbox.sqlite"), clock=lambda: now[0])
    items = [{"unique_id": "one", "title": "One"}]
    first = store.enqueue("https://feed", items, channel="webhook", destination="a")
    second = store.enqueue("https://feed", items, channel="smtp", destination="b")
    assert len(first) == len(second) == 1
    claimed = store.claim_due(channel="webhook", destination="a")
    assert claimed[0].attempts == 1
    store.fail(claimed[0].idempotency_key, "temporary", backoff=2)
    assert store.counts()["retry"] == 1
    now[0] += 3
    retried = store.claim_due(channel="webhook", destination="a")
    store.acknowledge(retried[0].idempotency_key)
    other = store.claim_due(channel="smtp", destination="b")
    store.fail(other[0].idempotency_key, "bad address", terminal=True)
    assert store.counts()["delivered"] == 1
    assert store.counts()["terminal"] == 1
    now[0] += 40 * 86400
    assert store.prune(30) == 1
    store.close()


def test_outbox_expired_claim_recovery(tmp_path):
    now = [10.0]
    store = DedupStore(str(tmp_path / "outbox.sqlite"), clock=lambda: now[0])
    store.enqueue("f", [{"unique_id": "1"}], channel="stdout", destination="stdout")
    store.claim_due(lease_seconds=2)
    now[0] += 3
    assert store.release_expired_claims() == 1
    assert store.claim_due()
    store.close()


def test_delivery_registry_stdout_and_webhook_classification():
    output = io.StringIO()
    stdout = StdoutChannel(stream=output)
    registry = DeliveryRegistry()
    registry.register(stdout)
    assert registry.names() == ("stdout",)
    payload = DeliveryPayload({"title": "Hi"}, {"title": "Feed"}, "key")
    assert registry.get("stdout").send(payload).successful
    assert '"Hi"' in output.getvalue()
    with pytest.raises(ValueError, match="unavailable"):
        registry.get("missing")

    retry = WebhookChannel(
        "https://example.com/hook",
        policy=FetchPolicy(block_private_hosts=False),
        session=FakeSession([FakeResponse(503)]),
    ).send(payload)
    assert retry.status == "retryable"
    terminal = WebhookChannel(
        "https://example.com/hook",
        policy=FetchPolicy(block_private_hosts=False),
        session=FakeSession([FakeResponse(400)]),
    ).send(payload)
    assert terminal.terminal


def test_smtp_channel_validation_and_retry(monkeypatch):
    channel = SMTPChannel("smtp.example", 587, "from@example", "to@example")
    channel.validate_config()

    class BrokenSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("offline")

    monkeypatch.setattr("newsworker.delivery.smtplib.SMTP", BrokenSMTP)
    result = channel.send(DeliveryPayload({"title": "x"}, {}, "key"))
    assert result.status == "retryable"
    with pytest.raises(ValueError):
        SMTPChannel("", 25, "", "").validate_config()


def test_smtp_success_terminal_size_and_login(monkeypatch):
    calls = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context=None):
            calls.append("tls")

        def login(self, username, password):
            calls.append((username, password))

        def send_message(self, message):
            calls.append(message["X-Newsworker-Idempotency-Key"])

    monkeypatch.setattr("newsworker.delivery.smtplib.SMTP", SMTP)
    channel = SMTPChannel(
        "smtp.example", 587, "from@example", "to@example", username="u", password="p"
    )
    assert channel.send(DeliveryPayload({"title": "x"}, {}, "key")).successful
    assert ("u", "p") in calls and "key" in calls
    tiny = SMTPChannel("smtp.example", 587, "from@example", "to@example", max_message_bytes=5)
    assert tiny.send(DeliveryPayload({"title": "large"}, {}, "key")).terminal

    class TerminalSMTP(SMTP):
        def send_message(self, message):
            import smtplib

            raise smtplib.SMTPDataError(550, b"rejected")

    monkeypatch.setattr("newsworker.delivery.smtplib.SMTP", TerminalSMTP)
    assert channel.send(DeliveryPayload({"title": "x"}, {}, "key")).terminal


def test_telegram_results_and_secret_redaction(monkeypatch):
    payload = DeliveryPayload({"title": "Hi", "link": "https://e"}, {}, "key")
    policy = FetchPolicy(block_private_hosts=False)
    channel = TelegramChannel("123:secret", "chat", policy)
    channel.validate_config()
    monkeypatch.setattr(
        "newsworker.delivery.RequestsTransport.fetch",
        lambda self, request, policy: FetchResult(request.url, request.url, 200, {}, b"{}"),
    )
    assert channel.send(payload).successful
    monkeypatch.setattr(
        "newsworker.delivery.RequestsTransport.fetch",
        lambda self, request, policy: FetchResult(request.url, request.url, 429, {}, b"{}"),
    )
    assert channel.send(payload).status == "retryable"
    monkeypatch.setattr(
        "newsworker.delivery.RequestsTransport.fetch",
        lambda self, request, policy: FetchResult(request.url, request.url, 400, {}, b"{}"),
    )
    assert channel.send(payload).terminal

    def fail(self, request, policy):
        raise RuntimeError("https://api.example/bot123:secret failed")

    monkeypatch.setattr("newsworker.delivery.RequestsTransport.fetch", fail)
    result = channel.send(payload)
    assert result.status == "retryable" and "123:secret" not in result.detail
    with pytest.raises(ValueError):
        TelegramChannel("", "", policy).validate_config()


def test_registry_entrypoints_and_webhook_wrapper(monkeypatch):
    class Point:
        name = "custom"

        def load(self):
            return StdoutChannel

    class Points(list):
        def select(self, **kwargs):
            return self

    monkeypatch.setattr(
        "newsworker.delivery.importlib.metadata.entry_points", lambda: Points([Point()])
    )
    registry = default_registry()
    assert registry.names() == ("stdout",)
    assert deliver_webhook("https://example.com", [], policy=FetchPolicy(block_private_hosts=False))

    responses = FakeSession(
        [FakeResponse(200), FakeResponse(400), FakeResponse(503), FakeResponse(503)]
    )
    assert deliver_webhook(
        "https://example.com",
        [{"title": "x"}],
        session=responses,
        policy=FetchPolicy(block_private_hosts=False),
    )
    assert not deliver_webhook(
        "https://example.com",
        [{"title": "x"}],
        session=responses,
        policy=FetchPolicy(block_private_hosts=False),
    )
    assert not deliver_webhook(
        "https://example.com",
        [{"title": "x"}],
        retries=2,
        backoff=0,
        session=responses,
        policy=FetchPolicy(block_private_hosts=False),
    )

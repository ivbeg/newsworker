import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from newsworker.delivery import (
    DeliveryPayload,
    DiscordChannel,
    MatrixChannel,
    SlackChannel,
    registry_from_settings,
)
from newsworker.fetch import FetchPolicy
from newsworker.settings import Settings

ITEM = {"title": "Rates <!channel> @everyone & more", "link": "https://news.example/1"}


class _Recorder(BaseHTTPRequestHandler):
    requests = []
    status = 200

    def log_message(self, *_args):
        pass

    def _record(self):
        length = int(self.headers.get("Content-Length") or 0)
        type(self).requests.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers),
                "body": json.loads(self.rfile.read(length) or b"{}"),
            }
        )
        self.send_response(type(self).status)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    do_POST = do_PUT = _record


@pytest.fixture
def hook():
    _Recorder.requests = []
    _Recorder.status = 200
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


POLICY = FetchPolicy(block_private_hosts=False, timeout=5)


def test_slack_escapes_mentions_and_links_the_title(hook):
    result = SlackChannel(hook + "/services/T/B/x", POLICY).send(DeliveryPayload(ITEM, {}, "k1"))
    assert result.successful
    text = _Recorder.requests[0]["body"]["text"]
    assert text == "<https://news.example/1|Rates &lt;!channel&gt; @everyone &amp; more>"


def test_discord_disables_mentions(hook):
    DiscordChannel(hook + "/api/webhooks/1/x", POLICY).send(DeliveryPayload(ITEM, {}, "k1"))
    body = _Recorder.requests[0]["body"]
    assert body["allowed_mentions"] == {"parse": []}
    assert body["content"].endswith("https://news.example/1")


def test_matrix_uses_the_idempotency_key_as_transaction_id(hook):
    channel = MatrixChannel(hook, "secret-token", "!room:example.org", POLICY)
    assert channel.send(DeliveryPayload(ITEM, {}, "outbox-key-1")).successful
    sent = _Recorder.requests[0]
    assert sent["method"] == "PUT"
    assert sent["path"].endswith("/rooms/%21room%3Aexample.org/send/m.room.message/outbox-key-1")
    assert sent["headers"]["Authorization"] == "Bearer secret-token"
    assert sent["body"]["msgtype"] == "m.text"


def test_failures_are_classified_and_secrets_never_leak(hook):
    _Recorder.status = 429
    assert (
        SlackChannel(hook + "/x", POLICY).send(DeliveryPayload(ITEM, {}, "k")).status == "retryable"
    )
    _Recorder.status = 404
    assert SlackChannel(hook + "/x", POLICY).send(DeliveryPayload(ITEM, {}, "k")).terminal
    unreachable = MatrixChannel("http://127.0.0.1:9", "tok-123456", "!r:x", POLICY)
    result = unreachable.send(DeliveryPayload(ITEM, {}, "k"))
    assert result.status == "retryable" and "tok-123456" not in (result.detail or "")


def test_registry_offers_configured_chat_channels():
    settings = Settings(
        slack_webhook_url="https://hooks.slack.com/services/T/B/secret",
        discord_webhook_url="https://discord.com/api/webhooks/1/secret",
        matrix_homeserver="https://matrix.example.org",
        matrix_token="tok",
        matrix_room="!room:example.org",
    )
    registry = registry_from_settings(settings)
    assert {"slack", "discord", "matrix"} <= set(registry.names())
    assert "secret" not in registry.get("slack").destination_identity
    redacted = settings.to_dict(redact=True)
    assert "secret" not in json.dumps(redacted)


def test_mastodon_posts_with_idempotency_key_and_defused_mentions(hook):
    from newsworker.delivery import MastodonChannel

    channel = MastodonChannel(hook, "secret-token", "unlisted", POLICY)
    assert channel.send(DeliveryPayload(ITEM, {}, "outbox-key-1")).successful
    sent = _Recorder.requests[0]
    assert sent["method"] == "POST" and sent["path"] == "/api/v1/statuses"
    assert sent["headers"]["Authorization"] == "Bearer secret-token"
    assert sent["headers"]["Idempotency-Key"] == "outbox-key-1"
    assert sent["body"]["visibility"] == "unlisted"
    assert "@everyone" not in sent["body"]["status"]
    assert sent["body"]["status"].endswith("\nhttps://news.example/1")
    assert "secret-token" not in channel.destination_identity


def test_mastodon_status_fits_the_character_limit(hook):
    from newsworker.delivery import MASTODON_LINK_CHARS, MASTODON_MAX_CHARS, MastodonChannel

    item = {"title": "x" * 900, "link": "https://news.example/" + "a" * 200}
    MastodonChannel(hook, "t", "public", POLICY).send(DeliveryPayload(item, {}, "k"))
    title, link = _Recorder.requests[0]["body"]["status"].split("\n")
    assert len(title) + 1 + MASTODON_LINK_CHARS <= MASTODON_MAX_CHARS
    assert title.endswith("…") and link == item["link"]


def test_mastodon_rejected_status_is_terminal(hook):
    from newsworker.delivery import MastodonChannel

    _Recorder.status = 422
    result = MastodonChannel(hook, "t", "public", POLICY).send(DeliveryPayload(ITEM, {}, "k"))
    assert result.terminal


def test_mastodon_settings(tmp_path):
    from newsworker.settings import SettingsError

    settings = Settings(
        cache_dir=str(tmp_path),
        mastodon_instance="https://mastodon.example",
        mastodon_token="tok",
    )
    assert "mastodon" in registry_from_settings(settings).names()
    assert settings.to_dict(redact=True)["mastodon_token"] != "tok"
    with pytest.raises(SettingsError):
        Settings(cache_dir=str(tmp_path), mastodon_visibility="everyone").validate()

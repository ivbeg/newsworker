import io
import json
import threading
import time
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from lxml.html import fromstring

from newsworker.batch import BatchResult, write_manifest
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
from newsworker.diagnostics import ExtractionDiagnostics, diagnostics_text
from newsworker.fetch import (
    AddressPolicyError,
    FetchPolicy,
    FetchRequest,
    FetchResult,
    RedirectPolicyError,
    RequestsTransport,
    ResponseTooLarge,
    URLPolicyError,
    validate_destination,
)
from newsworker.finder import FeedsFinder
from newsworker.language import LANGUAGE_SUPPORT, support_for
from newsworker.runtime import ExtractionContext, SingleFlight, closing_context
from newsworker.settings import Settings, SettingsError
from newsworker.sources import DocumentSource, DocumentSourceError
from newsworker.spec import FeedSpec, SpecValidationError, validate_spec_dict
from newsworker.tools import resolve_feed_language_with_diagnostics
from newsworker.undated import extract_undated_listing


def test_settings_precedence_immutability_and_sources(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("content_ttl: 20\nuser_agent: yaml-agent\n", encoding="utf-8")
    resolved = Settings.resolve(
        str(path),
        environ={"NEWSWORKER_CONTENT_TTL": "30"},
        cli={"content_ttl": 40},
    )
    assert resolved.content_ttl == 40
    assert resolved.user_agent == "yaml-agent"
    assert resolved.source_for("content_ttl") == "cli"
    with pytest.raises(FrozenInstanceError):
        resolved.content_ttl = 10


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NEWSWORKER_VERIFY_TLS", "false"),
        ("NEWSWORKER_ALLOWED_HOSTS", "a.example,b.example"),
        ("NEWSWORKER_EXTRA_HEADERS", '{"X-Test":"1"}'),
        ("NEWSWORKER_REQUEST_TIMEOUT", "9"),
    ],
)
def test_environment_parsing(name, value):
    settings = Settings.resolve(environ={name: value})
    if name.endswith("VERIFY_TLS"):
        assert settings.verify_tls is False
    elif name.endswith("ALLOWED_HOSTS"):
        assert settings.allowed_hosts == ["a.example", "b.example"]
    elif name.endswith("EXTRA_HEADERS"):
        assert settings.extra_headers == {"X-Test": "1"}
    else:
        assert settings.request_timeout == 9


@pytest.mark.parametrize(
    "settings,match",
    [
        (Settings(port=0), "port"),
        (Settings(request_timeout=0), "request_timeout"),
        (Settings(default_timezone="Not/AZone"), "default_timezone"),
        (Settings(proxy="broken"), "proxy"),
        (Settings(extra_headers={"bad header": "x"}), "header"),
        (Settings(extra_headers={"X-Test": "bad\nvalue"}), "newline"),
        (Settings(allowed_hosts=["https://bad"]), "allowed host"),
        (Settings(cors_allowed_origins=["*bad"]), "CORS"),
        (Settings(undated_min_confidence=2), "confidence"),
    ],
)
def test_settings_validation(settings, match):
    with pytest.raises(SettingsError, match=match):
        settings.validate()


def test_settings_redacts_secrets():
    settings = Settings(
        api_tokens=["secret"],
        proxy="https://user:pass@example.com",
        smtp_password="pw",
        telegram_token="token",
        extra_headers={"Authorization": "Bearer secret", "Accept": "text/html"},
    )
    data = settings.to_dict(redact=True)
    assert data["api_tokens"] == "<redacted>"
    assert data["extra_headers"]["Authorization"] == "<redacted>"
    assert data["extra_headers"]["Accept"] == "text/html"


def test_spec_validation_precise_errors():
    with pytest.raises(SpecValidationError, match="unsupported spec version"):
        validate_spec_dict({"version": 2})
    with pytest.raises(SpecValidationError, match="items.selector_type"):
        validate_spec_dict({"version": 1, "items": {"selector_type": "regex"}})
    with pytest.raises(SpecValidationError, match="fields.title.source"):
        validate_spec_dict(
            {
                "version": 1,
                "items": {"selector": "article"},
                "fields": {"title": {"source": "magic"}},
            }
        )
    assert FeedSpec().validate() is not None


def test_document_sources_file_stdin_and_errors(tmp_path):
    path = tmp_path / "page.html"
    path.write_bytes(b"<html><a href='/x'>x</a></html>")
    source = DocumentSource.file(str(path), base_url="https://example.com/archive")
    assert source.is_local and source.data.startswith(b"<html")
    stdin = DocumentSource.stdin(
        base_url="https://example.com/base", stream=io.BytesIO(b"<html>stdin</html>")
    )
    assert stdin.kind == "stdin"
    assert DocumentSource.url("https://example.com").kind == "url"
    with pytest.raises(DocumentSourceError, match="regular file"):
        DocumentSource.file(str(tmp_path / "missing"), base_url="https://example.com")
    with pytest.raises(DocumentSourceError, match="empty"):
        DocumentSource.stdin(base_url="https://example.com", stream=io.BytesIO())


def test_diagnostics_score_serialize_and_text():
    diagnostic = ExtractionDiagnostics(source="file", requested_url="https://e")
    diagnostic.start("parse")
    diagnostic.stop("parse")
    diagnostic.add_attempt("spec", "success", item_count=3, selectors={"items": "article"})
    feed = {
        "items": [
            {"title": "a", "link": "https://e/a", "pubdate": "date"},
            {"title": "b", "link": "https://e/b", "pubdate": "date"},
            {"title": "c", "link": "https://e/c", "pubdate": "date"},
        ]
    }
    assert diagnostic.score(feed) == 1.0
    diagnostic.chosen_strategy = "spec"
    assert diagnostic.to_dict()["attempts"][0]["strategy"] == "spec"
    assert "confidence: 1.000" in diagnostics_text(diagnostic)
    empty = ExtractionDiagnostics()
    assert empty.score({"items": []}) == 0
    assert "No items" in empty.warnings[0]


def test_language_override_and_ambiguous_diagnostics():
    language, details = resolve_feed_language_with_diagnostics(override="fr-FR")
    assert (language, details["reason"]) == ("fr", "explicit_override")
    language, details = resolve_feed_language_with_diagnostics()
    assert language == "en" and details["ambiguous"] is True
    doc = fromstring("<html lang='en'><body></body></html>")
    _, details = resolve_feed_language_with_diagnostics(
        document=doc, text_samples=["Важная новость экономики России сегодня"]
    )
    assert details["reason"] == "ambiguous_evidence"
    assert support_for("fr-FR").extraction == "supported"
    assert LANGUAGE_SUPPORT["ja"].extraction == "partial"


def test_singleflight_coalesces_same_key_and_propagates_errors():
    flight = SingleFlight()
    barrier = threading.Barrier(5)
    calls = []

    def expensive():
        calls.append(1)
        time.sleep(0.03)
        return "value"

    results = []

    def worker():
        barrier.wait()
        results.append(flight.call("same", expensive))

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == ["value"] * 5
    assert len(calls) == 1 and flight.active_keys == 0
    with pytest.raises(RuntimeError, match="boom"):
        flight.call("bad", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    error_barrier = threading.Barrier(3)
    errors = []

    def failing():
        time.sleep(0.02)
        raise RuntimeError("shared failure")

    def error_worker():
        error_barrier.wait()
        try:
            flight.call("shared-error", failing)
        except RuntimeError as exc:
            errors.append(str(exc))

    error_threads = [threading.Thread(target=error_worker) for _ in range(2)]
    for thread in error_threads:
        thread.start()
    error_barrier.wait()
    for thread in error_threads:
        thread.join()
    assert errors == ["shared failure", "shared failure"]
    assert flight.active_keys == 0


def test_context_cleanup():
    context = ExtractionContext()
    context.session = {"debug": {}}
    with closing_context(context):
        assert context.date_parser is not None
    assert context.session is None and context._date_parser is None


class FakeResponse:
    def __init__(self, status=200, headers=None, chunks=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks or [b"ok"]

    def iter_content(self, chunk_size=65536):
        return iter(self._chunks)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(str(self.status_code))

    def close(self):
        pass


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_fetch_policy_blocks_special_addresses_and_credentials():
    policy = FetchPolicy()
    for url in (
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.1.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
    ):
        with pytest.raises(AddressPolicyError):
            validate_destination(url, policy)
    with pytest.raises(URLPolicyError, match="Credentials"):
        validate_destination("https://user:pass@example.com", policy)
    with pytest.raises(URLPolicyError, match="scheme"):
        validate_destination("file:///etc/passwd", policy)


def test_explicit_private_allowlist_opt_in():
    policy = FetchPolicy(allowed_hosts=("127.0.0.1",), allow_private_hosts=True)
    assert validate_destination("http://127.0.0.1/x", policy) == "127.0.0.1"
    with pytest.raises(URLPolicyError, match="allowed"):
        validate_destination("https://example.com", policy)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.1/",
        "http://2130706433/",
        "http://0x7f000001/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::]/",
    ],
)
def test_ssrf_encoded_and_mapped_address_corpus(url, monkeypatch):
    monkeypatch.setattr(
        "newsworker.fetch.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    with pytest.raises(AddressPolicyError):
        validate_destination(url, FetchPolicy())


def test_dns_change_is_rechecked_before_redirect_request(monkeypatch):
    import ipaddress

    resolutions = iter(
        [
            (ipaddress.ip_address("93.184.216.34"),),
            (ipaddress.ip_address("127.0.0.1"),),
        ]
    )
    monkeypatch.setattr("newsworker.fetch.classify_addresses", lambda host: next(resolutions))
    session = FakeSession([FakeResponse(302, {"Location": "/changed"})])
    with pytest.raises(AddressPolicyError):
        RequestsTransport(session).fetch(FetchRequest("https://example.com/start"), FetchPolicy())
    assert len(session.calls) == 1


def test_requests_transport_redirect_metadata_and_post():
    session = FakeSession(
        [
            FakeResponse(302, {"Location": "/final"}),
            FakeResponse(200, {"ETag": '"v1"', "Content-Language": "fr-FR"}, [b"body"]),
            FakeResponse(202, {}, [b"accepted"]),
        ]
    )
    transport = RequestsTransport(session)
    cookies = {"session": "value"}
    policy = FetchPolicy(
        block_private_hosts=False,
        redirect_limit=2,
        timeout=9,
        verify_tls=False,
        proxy="http://proxy.example:8080",
        user_agent="test-agent",
        extra_headers={"X-Test": "yes"},
        cookies=cookies,
    )
    result = transport.fetch(FetchRequest("https://example.com/start"), policy)
    assert result.body == b"body" and result.effective_url.endswith("/final")
    assert result.validators == {"etag": '"v1"'}
    assert result.content_language == "fr-FR"
    request_options = session.calls[0][2]
    assert request_options["timeout"] == 9
    assert request_options["verify"] is False
    assert request_options["proxies"] == {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }
    assert request_options["cookies"] is cookies
    assert request_options["headers"]["User-agent"] == "test-agent"
    assert request_options["headers"]["X-Test"] == "yes"
    posted = transport.fetch(
        FetchRequest("https://example.com/hook", method="POST", body=b"{}", operation="delivery"),
        policy,
    )
    assert posted.status == 202 and session.calls[-1][0] == "POST"


def test_requests_transport_limits_redirects_and_bodies():
    policy = FetchPolicy(block_private_hosts=False, max_bytes=3, redirect_limit=0)
    with pytest.raises(RedirectPolicyError):
        RequestsTransport(FakeSession([FakeResponse(302, {"Location": "/again"})])).fetch(
            FetchRequest("https://example.com"), policy
        )
    with pytest.raises(ResponseTooLarge):
        RequestsTransport(FakeSession([FakeResponse(chunks=[b"1234"])])).fetch(
            FetchRequest("https://example.com"), policy
        )
    not_modified = RequestsTransport(FakeSession([FakeResponse(304)])).fetch(
        FetchRequest("https://example.com"), policy
    )
    assert not_modified.not_modified


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


def test_manifest_json_csv(tmp_path):
    records = [
        BatchResult("https://a", "success", output_path="a.json", item_count=2),
        BatchResult("https://b", "failure", error_type="Timeout", error="timed out"),
    ]
    json_path = tmp_path / "manifest.json"
    csv_path = tmp_path / "manifest.csv"
    write_manifest(records, str(json_path), "json")
    write_manifest(records, str(csv_path), "csv")
    assert json.loads(json_path.read_text())[1]["status"] == "failure"
    assert "error_type" in csv_path.read_text()
    with pytest.raises(ValueError):
        write_manifest(records, str(tmp_path / "x"), "xml")


def test_undated_listing_and_false_positive_guards():
    cards = "".join(
        f"<article class='news-card'><h2><a href='/story/{index}'>Important headline number {index}</a></h2><p>Useful summary for story {index}</p></article>"
        for index in range(4)
    )
    feed, details = extract_undated_listing(
        f"<html><head><title>News</title></head><body><main>{cards}</main></body></html>".encode(),
        "https://example.com/news",
    )
    assert len(feed["items"]) == 4
    assert all(item["pubdate"] is None for item in feed["items"])
    assert (
        feed["items"][0]["unique_id"]
        == extract_undated_listing(
            f"<html><body><main>{cards}</main></body></html>".encode(),
            "https://example.com/news",
        )[0]["items"][0]["unique_id"]
    )
    assert details["confidence"] >= 0.75

    navigation = "".join(
        f"<h2><a href='/{index}'>Navigation option {index}</a></h2>" for index in range(5)
    )
    rejected, _ = extract_undated_listing(
        f"<html><body><nav>{navigation}</nav></body></html>".encode(),
        "https://example.com",
    )
    assert rejected["items"] == []


def test_undated_labeled_corpus_precision_and_recall():
    corpus_path = Path(__file__).parent / "fixtures" / "undated" / "corpus.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    outcomes = []
    for case in corpus:
        feed, _ = extract_undated_listing(
            case["html"].encode("utf-8"),
            f"https://example.com/{case['name'].replace(' ', '-')}",
        )
        outcomes.append((case["label"], bool(feed["items"])))
    true_positive = sum(expected and actual for expected, actual in outcomes)
    false_positive = sum(not expected and actual for expected, actual in outcomes)
    false_negative = sum(expected and not actual for expected, actual in outcomes)
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    assert precision >= 0.9
    assert recall >= 0.9


class MapTransport:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def fetch(self, request, policy):
        self.calls.append(request.url)
        value = self.mapping[request.url]
        if isinstance(value, Exception):
            raise value
        body, headers = value
        return FetchResult(request.url, request.url, 200, headers, body)


def test_modern_discovery_jsonfeed_websub_and_sitemap_indexes():
    html = b"""<html><head>
      <link rel='alternate stylesheet' type='application/feed+json' href='/feed.json' title='JSON'>
      <link rel='alternate' type='application/atom+xml' href='/atom.xml'>
    </head></html>"""
    json_feed = json.dumps(
        {
            "version": "https://jsonfeed.org/version/1.1",
            "title": "JSON News",
            "items": [{"id": "1", "content_text": "hello"}],
            "hubs": [{"type": "WebSub", "url": "https://hub.example"}],
        }
    ).encode()
    atom = b"""<feed xmlns='http://www.w3.org/2005/Atom'><title>A</title>
      <link rel='self' href='https://example.com/atom.xml'/>
      <link rel='hub' href='https://hub.example'/><entry><id>1</id><title>x</title></entry></feed>"""
    index = b"""<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <sitemap><loc>https://example.com/nested.xml</loc></sitemap></sitemapindex>"""
    nested = b"""<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
      <url><loc>https://example.com/feed.json</loc></url></urlset>"""
    transport = MapTransport(
        {
            "https://example.com/": (html, {"Content-Type": "text/html"}),
            "https://example.com/feed.json": (json_feed, {"Content-Type": "application/feed+json"}),
            "https://example.com/atom.xml": (atom, {"Content-Type": "application/atom+xml"}),
            "https://example.com/sitemap.xml": (index, {}),
            "https://example.com/nested.xml": (nested, {}),
        }
    )
    finder = FeedsFinder(Settings(block_private_hosts=False), transport=transport)
    results = finder.find_feeds("https://example.com/", noverify=False, include_sitemap=True)
    by_type = {item["feedtype"]: item for item in results["items"]}
    assert by_type["jsonfeed"]["verification"] == "valid"
    assert by_type["atom"]["hubs"] == ["https://hub.example"]
    assert "https://example.com/nested.xml" in transport.calls


def test_discovery_invalid_candidate_does_not_abort_others():
    html = b"<html><head><link rel='alternate' type='application/feed+json' href='/bad.json'><link rel='alternate' type='application/rss+xml' href='/ok.xml'></head></html>"
    rss = b"<rss version='2.0'><channel><title>OK</title><item><title>x</title></item></channel></rss>"
    transport = MapTransport(
        {
            "https://example.com/": (html, {"Content-Type": "text/html"}),
            "https://example.com/bad.json": (b"{}", {"Content-Type": "application/feed+json"}),
            "https://example.com/ok.xml": (rss, {"Content-Type": "application/rss+xml"}),
        }
    )
    results = FeedsFinder(Settings(block_private_hosts=False), transport).find_feeds(
        "https://example.com/", noverify=False
    )
    states = {item["url"]: item["verification"] for item in results["items"]}
    assert states["https://example.com/bad.json"] == "invalid"
    assert states["https://example.com/ok.xml"] == "valid"

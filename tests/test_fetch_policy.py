"""The shared outbound fetch policy and the requests transport."""

import pytest
from http_fakes import FakeResponse, FakeSession

from newsworker.fetch import (
    AddressPolicyError,
    FetchPolicy,
    FetchRequest,
    RedirectPolicyError,
    RequestsTransport,
    ResponseTooLarge,
    URLPolicyError,
    validate_destination,
)


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

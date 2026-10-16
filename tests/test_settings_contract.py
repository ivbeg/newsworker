"""Layered settings: precedence, environment parsing, validation, redaction."""

from dataclasses import FrozenInstanceError

import pytest

from newsworker.settings import Settings, SettingsError


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

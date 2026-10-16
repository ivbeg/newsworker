#!/usr/bin/env python
"""Extensible delivery channels with centralized result classification."""

from __future__ import annotations

import datetime
import hashlib
import importlib.metadata
import json
import logging
import re
import smtplib
import ssl
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Protocol, cast
from urllib.parse import quote

from .fetch import FetchPolicy, FetchRequest, RequestsTransport
from .formats import _date_handler, format_feed
from .model import Feed, Item
from .tools import validate_url

log = logging.getLogger(__name__)
ENTRY_POINT_GROUP = "newsworker.delivery"


@dataclass(frozen=True)
class ChannelCapabilities:
    supports_idempotency: bool = False
    max_message_bytes: int = 1024 * 1024
    rich_text: bool = False


@dataclass(frozen=True)
class DeliveryPayload:
    item: Mapping[str, Any]
    feed: Mapping[str, Any]
    idempotency_key: str


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    detail: str = ""
    provider_id: str | None = None

    @property
    def successful(self) -> bool:
        return self.status == "success"

    @property
    def terminal(self) -> bool:
        return self.status == "terminal"


class DeliveryChannel(Protocol):
    name: str
    capabilities: ChannelCapabilities

    @property
    def destination_identity(self) -> str: ...

    def validate_config(self) -> None: ...
    def send(self, payload: DeliveryPayload) -> DeliveryResult: ...


class DeliveryRegistry:
    def __init__(self):
        self._channels: dict[str, DeliveryChannel] = {}

    def register(self, channel: DeliveryChannel) -> None:
        self._channels[channel.name] = channel

    def get(self, name: str) -> DeliveryChannel:
        if name not in self._channels:
            raise ValueError(
                f"Delivery channel {name!r} is unavailable; install its optional extra or entry point"
            )
        channel = self._channels[name]
        channel.validate_config()
        return channel

    def names(self):
        return tuple(sorted(self._channels))

    def load_entry_points(self) -> None:
        try:
            points = importlib.metadata.entry_points()
            group = (
                points.select(group=ENTRY_POINT_GROUP)
                if hasattr(points, "select")
                else points.get(ENTRY_POINT_GROUP, ())
            )
        except Exception as exc:
            log.debug("Could not enumerate delivery entry points: %s", exc)
            return
        for point in sorted(group, key=lambda item: item.name):
            try:
                loaded = point.load()
                self.register(loaded() if isinstance(loaded, type) else loaded)
            except Exception as exc:
                log.warning("Failed to load delivery channel %s: %s", point.name, exc)


@dataclass
class StdoutChannel:
    """Write new items to a stream.

    ``json`` (the default) writes one JSON object per line (JSON Lines). Any
    other feed format writes one document per poll containing that poll's new
    items, e.g. ``watch --format rss``.
    """

    stream: Any = sys.stdout
    name: str = "stdout"
    fmt: str = "json"
    capabilities: ChannelCapabilities = field(default_factory=lambda: ChannelCapabilities())

    @property
    def destination_identity(self) -> str:
        return "stdout"

    def validate_config(self) -> None:
        if not hasattr(self.stream, "write"):
            raise ValueError("stdout channel stream is not writable")

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        return self.send_batch([payload])[0]

    def send_batch(self, payloads: list[DeliveryPayload]) -> list[DeliveryResult]:
        if not payloads:
            return []
        try:
            if self.fmt in ("json", "jsonl"):
                for payload in payloads:
                    self.stream.write(
                        json.dumps(payload.item, default=_date_handler, ensure_ascii=False) + "\n"
                    )
            else:
                feed = cast(Feed, dict(payloads[0].feed))
                feed["items"] = [cast(Item, restore_item(payload.item)) for payload in payloads]
                self.stream.write(format_feed(feed, fmt=self.fmt))
            self.stream.flush()
        except Exception as exc:  # noqa: BLE001
            return [DeliveryResult("retryable", _safe_error(exc)) for _ in payloads]
        return [DeliveryResult("success") for _ in payloads]


def restore_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Turn a JSON-serialised outbox item back into the internal item shape."""
    restored = dict(item)
    value = restored.get("pubdate")
    if isinstance(value, str):
        try:
            restored["pubdate"] = datetime.datetime.fromisoformat(value)
        except ValueError:
            restored["pubdate"] = None
    return restored


@dataclass
class WebhookChannel:
    url: str
    timeout: float = 30
    policy: FetchPolicy | None = None
    session: Any = None
    name: str = "webhook"
    capabilities: ChannelCapabilities = field(
        default_factory=lambda: ChannelCapabilities(supports_idempotency=True)
    )

    @property
    def destination_identity(self) -> str:
        # URLs often contain credentials in query parameters. Persist only a
        # stable opaque identity in the outbox.
        return "webhook:" + hashlib.sha256(self.url.encode("utf-8")).hexdigest()[:24]

    def validate_config(self) -> None:
        validate_url(self.url)

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        body = json.dumps(
            {"feed": dict(payload.feed), "items": [dict(payload.item)]},
            default=_date_handler,
            ensure_ascii=False,
        ).encode("utf-8")
        policy = self.policy or FetchPolicy(timeout=self.timeout, user_agent="newsworker")
        try:
            result = RequestsTransport(self.session).fetch(
                FetchRequest(
                    self.url,
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Idempotency-Key": payload.idempotency_key,
                    },
                    body=body,
                    operation="delivery",
                ),
                policy,
            )
        except Exception as exc:
            return DeliveryResult("retryable", _safe_error(exc))
        if 200 <= result.status < 300:
            return DeliveryResult("success")
        if result.status in {408, 425, 429} or result.status >= 500:
            return DeliveryResult("retryable", f"HTTP {result.status}")
        return DeliveryResult("terminal", f"HTTP {result.status}")


@dataclass
class SMTPChannel:
    host: str
    port: int
    sender: str
    recipient: str
    username: str = ""
    password: str = ""
    timeout: float = 30
    max_message_bytes: int = 1024 * 1024
    name: str = "smtp"
    capabilities: ChannelCapabilities = field(default_factory=lambda: ChannelCapabilities())

    @property
    def destination_identity(self) -> str:
        return f"smtp:{self.recipient.lower()}"

    def validate_config(self) -> None:
        if not self.host or not self.sender or not self.recipient:
            raise ValueError("SMTP host, sender, and recipient are required")

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        title = (
            str(payload.item.get("title") or "News update").replace("\r", " ").replace("\n", " ")
        )
        link = str(payload.item.get("link") or "")
        description = str(payload.item.get("description") or "")
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = self.recipient
        message["Subject"] = title[:200]
        message["X-Newsworker-Idempotency-Key"] = payload.idempotency_key
        message.set_content(f"{title}\n\n{description}\n\n{link}"[: self.max_message_bytes])
        if len(message.as_bytes()) > self.max_message_bytes:
            return DeliveryResult("terminal", "rendered email exceeds configured size")
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(message)
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as exc:
            return DeliveryResult("retryable", _safe_error(exc))
        except smtplib.SMTPResponseException as exc:
            return DeliveryResult("terminal", _safe_error(exc))
        except smtplib.SMTPException as exc:
            return DeliveryResult("terminal", _safe_error(exc))
        except OSError as exc:
            return DeliveryResult("retryable", _safe_error(exc))
        return DeliveryResult("success")


def _item_text(item: Mapping[str, Any]) -> tuple:
    title = str(item.get("title") or "News update")
    if item.get("updated"):
        title = "Updated: " + title
    return title, str(item.get("link") or "")


def _send_json(
    url: str,
    body: Mapping[str, Any],
    policy: FetchPolicy | None,
    *,
    method: str = "POST",
    headers: Mapping[str, str] | None = None,
    secrets: tuple = (),
) -> DeliveryResult:
    """Send one JSON delivery request and classify the outcome.

    2xx is success; 408/425/429 and 5xx are retried; anything else is
    terminal. ``secrets`` are scrubbed from error text kept in the outbox.
    """
    try:
        result = RequestsTransport().fetch(
            FetchRequest(
                url,
                method=method,
                headers={"Content-Type": "application/json", **dict(headers or {})},
                body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                operation="delivery",
            ),
            policy or FetchPolicy(user_agent="newsworker"),
        )
    except Exception as exc:
        detail = _safe_error(exc)
        for secret in secrets:
            if secret:
                detail = detail.replace(secret, "<redacted>")
        return DeliveryResult("retryable", detail)
    if 200 <= result.status < 300:
        return DeliveryResult("success")
    if result.status in {408, 425, 429} or result.status >= 500:
        return DeliveryResult("retryable", f"HTTP {result.status}")
    return DeliveryResult("terminal", f"HTTP {result.status}")


def _opaque(kind: str, secret: str) -> str:
    """Stable outbox identity for a destination whose address is a secret."""
    return f"{kind}:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:24]


@dataclass
class TelegramChannel:
    token: str
    chat_id: str
    policy: FetchPolicy
    name: str = "telegram"
    capabilities: ChannelCapabilities = field(
        default_factory=lambda: ChannelCapabilities(max_message_bytes=4096, rich_text=False)
    )

    @property
    def destination_identity(self) -> str:
        return f"telegram:{self.chat_id}"

    def validate_config(self) -> None:
        if not self.token or not self.chat_id:
            raise ValueError("Telegram token and chat_id are required")

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        title, link = _item_text(payload.item)
        # Plain text (no parse_mode): page titles cannot inject markup.
        text = "\n".join(filter(None, [title, link]))[:4096]
        url = f"https://api.telegram.org/bot{quote(self.token, safe='')}/sendMessage"
        return _send_json(
            url, {"chat_id": self.chat_id, "text": text}, self.policy, secrets=(self.token,)
        )


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class SlackChannel:
    """Slack incoming webhook. Titles are escaped, so ``<!channel>`` cannot ping."""

    webhook_url: str
    policy: FetchPolicy | None = None
    name: str = "slack"
    capabilities: ChannelCapabilities = field(default_factory=lambda: ChannelCapabilities())

    @property
    def destination_identity(self) -> str:
        return _opaque("slack", self.webhook_url)

    def validate_config(self) -> None:
        validate_url(self.webhook_url)

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        title, link = _item_text(payload.item)
        text = f"<{link}|{_slack_escape(title)}>" if link else _slack_escape(title)
        return _send_json(
            self.webhook_url, {"text": text}, self.policy, secrets=(self.webhook_url,)
        )


@dataclass
class DiscordChannel:
    """Discord webhook. Mentions are disabled, so ``@everyone`` in a title is inert."""

    webhook_url: str
    policy: FetchPolicy | None = None
    name: str = "discord"
    capabilities: ChannelCapabilities = field(
        default_factory=lambda: ChannelCapabilities(max_message_bytes=2000)
    )

    @property
    def destination_identity(self) -> str:
        return _opaque("discord", self.webhook_url)

    def validate_config(self) -> None:
        validate_url(self.webhook_url)

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        title, link = _item_text(payload.item)
        content = "\n".join(filter(None, [title, link]))[:2000]
        body = {"content": content, "allowed_mentions": {"parse": []}}
        return _send_json(self.webhook_url, body, self.policy, secrets=(self.webhook_url,))


@dataclass
class MatrixChannel:
    """Matrix room message. The outbox idempotency key is the Matrix
    transaction id, so a retried send is de-duplicated by the homeserver."""

    homeserver: str
    token: str
    room_id: str
    policy: FetchPolicy | None = None
    name: str = "matrix"
    capabilities: ChannelCapabilities = field(
        default_factory=lambda: ChannelCapabilities(supports_idempotency=True)
    )

    @property
    def destination_identity(self) -> str:
        return f"matrix:{self.room_id}"

    def validate_config(self) -> None:
        if not self.token or not self.room_id:
            raise ValueError("Matrix token and room id are required")
        validate_url(self.homeserver)

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        title, link = _item_text(payload.item)
        url = (
            f"{self.homeserver.rstrip('/')}/_matrix/client/v3/rooms/"
            f"{quote(self.room_id, safe='')}/send/m.room.message/"
            f"{quote(payload.idempotency_key, safe='')}"
        )
        body = {"msgtype": "m.text", "body": "\n".join(filter(None, [title, link]))}
        return _send_json(
            url,
            body,
            self.policy,
            method="PUT",
            headers={"Authorization": f"Bearer {self.token}"},
            secrets=(self.token,),
        )


#: Mastodon's default post limit; every link counts as 23 characters.
MASTODON_MAX_CHARS = 500
MASTODON_LINK_CHARS = 23


def _defuse_mentions(text: str) -> str:
    """Break ``@user@instance`` so a page title cannot notify anyone."""
    return text.replace("@", "@\u200b")


@dataclass
class MastodonChannel:
    """A status on a Mastodon (or compatible) account.

    The outbox idempotency key is sent as ``Idempotency-Key``, so a retried
    post is de-duplicated by the server. Mentions in titles are defused.
    """

    instance: str
    token: str
    visibility: str = "unlisted"
    policy: FetchPolicy | None = None
    name: str = "mastodon"
    capabilities: ChannelCapabilities = field(
        default_factory=lambda: ChannelCapabilities(
            max_message_bytes=MASTODON_MAX_CHARS * 4, supports_idempotency=True
        )
    )

    @property
    def destination_identity(self) -> str:
        # The account is the destination; its token is secret, so hash both.
        return _opaque("mastodon", self.instance.rstrip("/").lower() + "\n" + self.token)

    def validate_config(self) -> None:
        if not self.token:
            raise ValueError("Mastodon token is required")
        validate_url(self.instance)

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        title, link = _item_text(payload.item)
        room = MASTODON_MAX_CHARS - (MASTODON_LINK_CHARS + 1 if link else 0)
        title = _defuse_mentions(title)
        if len(title) > room:
            title = title[: room - 1].rstrip() + "…"
        status = "\n".join(filter(None, [title, link]))
        return _send_json(
            f"{self.instance.rstrip('/')}/api/v1/statuses",
            {"status": status, "visibility": self.visibility},
            self.policy,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Idempotency-Key": payload.idempotency_key,
            },
            secrets=(self.token,),
        )


def default_registry() -> DeliveryRegistry:
    registry = DeliveryRegistry()
    registry.register(StdoutChannel())
    registry.load_entry_points()
    return registry


def registry_from_settings(
    settings,
    *,
    webhook_url="",
    smtp_recipient="",
    telegram_chat_id="",
):
    """Build the deterministic built-in registry for configured destinations."""
    registry = default_registry()
    if webhook_url:
        from .fetch import policy_from_settings

        registry.register(
            WebhookChannel(
                webhook_url,
                timeout=settings.request_timeout,
                policy=policy_from_settings(settings, operation="delivery"),
            )
        )
    if smtp_recipient:
        registry.register(
            SMTPChannel(
                settings.smtp_host,
                settings.smtp_port,
                settings.smtp_from,
                smtp_recipient,
                username=settings.smtp_username,
                password=settings.smtp_password,
                timeout=settings.request_timeout,
            )
        )
    from .fetch import policy_from_settings

    policy = policy_from_settings(settings, operation="delivery")
    if telegram_chat_id:
        registry.register(TelegramChannel(settings.telegram_token, telegram_chat_id, policy))
    if getattr(settings, "slack_webhook_url", ""):
        registry.register(SlackChannel(settings.slack_webhook_url, policy))
    if getattr(settings, "discord_webhook_url", ""):
        registry.register(DiscordChannel(settings.discord_webhook_url, policy))
    if getattr(settings, "matrix_room", ""):
        registry.register(
            MatrixChannel(
                settings.matrix_homeserver, settings.matrix_token, settings.matrix_room, policy
            )
        )
    if getattr(settings, "mastodon_instance", ""):
        registry.register(
            MastodonChannel(
                settings.mastodon_instance,
                settings.mastodon_token,
                getattr(settings, "mastodon_visibility", "unlisted"),
                policy,
            )
        )
    return registry


def deliver_webhook(
    url,
    items,
    feed=None,
    retries=3,
    backoff=1.0,
    timeout=30,
    session=None,
    idempotency_key=None,
    policy=None,
):
    """Backward-compatible webhook helper using destination policy semantics."""
    validate_url(url)
    if not items:
        return True
    # Preserve simple injected test clients while production uses the policy adapter.
    if session is not None and hasattr(session, "post") and not hasattr(session, "request"):
        body = json.dumps(
            {
                "feed": {"title": (feed or {}).get("title"), "link": (feed or {}).get("link")},
                "items": items,
            },
            default=_date_handler,
            ensure_ascii=False,
        ).encode("utf-8")
        for attempt in range(retries):
            response = session.post(
                url, data=body, headers={"Content-Type": "application/json"}, timeout=timeout
            )
            if 200 <= response.status_code < 300:
                return True
            if attempt + 1 < retries:
                time.sleep(backoff * (attempt + 1))
        return False
    # Each item is a separate request, so each needs its own idempotency key; a
    # receiver honouring one shared key would drop every item after the first.
    keys = [
        hashlib.sha256(
            "\x1f".join(
                (
                    idempotency_key or url,
                    json.dumps(item, default=_date_handler, sort_keys=True),
                )
            ).encode("utf-8")
        ).hexdigest()
        for item in items
    ]
    channel = WebhookChannel(url=url, timeout=timeout, policy=policy, session=session)
    channel.validate_config()
    remaining = list(zip(items, keys, strict=True))
    for attempt in range(retries):
        failed = []
        for item, key in remaining:
            result = channel.send(DeliveryPayload(item, feed or {}, key))
            if result.terminal:
                return False
            if not result.successful:
                failed.append((item, key))
        if not failed:
            return True
        remaining = failed  # retry only the units that failed, with stable keys
        if attempt + 1 < retries:
            time.sleep(backoff * (attempt + 1))
    return False


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(r"(https?://)([^/@\s]+)@", r"\1<redacted>@", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1<redacted>", text)
    text = re.sub(r"(?i)(bot)[0-9]+:[A-Za-z0-9_-]+", r"\1<redacted>", text)
    return text[:1000]

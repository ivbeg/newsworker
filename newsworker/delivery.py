#!/usr/bin/env python
"""Extensible delivery channels with centralized result classification."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import re
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Dict, Mapping, Optional, Protocol
from urllib.parse import quote

from .fetch import FetchPolicy, FetchRequest, RequestsTransport
from .formats import _date_handler
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
    provider_id: Optional[str] = None

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
        self._channels: Dict[str, DeliveryChannel] = {}

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
    stream: Any = sys.stdout
    name: str = "stdout"
    capabilities: ChannelCapabilities = field(default_factory=lambda: ChannelCapabilities())

    @property
    def destination_identity(self) -> str:
        return "stdout"

    def validate_config(self) -> None:
        if not hasattr(self.stream, "write"):
            raise ValueError("stdout channel stream is not writable")

    def send(self, payload: DeliveryPayload) -> DeliveryResult:
        self.stream.write(
            json.dumps(payload.item, default=_date_handler, ensure_ascii=False) + "\n"
        )
        self.stream.flush()
        return DeliveryResult("success")


@dataclass
class WebhookChannel:
    url: str
    timeout: float = 30
    policy: Optional[FetchPolicy] = None
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
        text = "\n".join(
            filter(
                None,
                [
                    str(payload.item.get("title") or "News update"),
                    str(payload.item.get("link") or ""),
                ],
            )
        )[:4096]
        body = json.dumps({"chat_id": self.chat_id, "text": text}).encode("utf-8")
        url = f"https://api.telegram.org/bot{quote(self.token, safe='')}/sendMessage"
        try:
            result = RequestsTransport().fetch(
                FetchRequest(
                    url,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                    body=body,
                    operation="delivery",
                ),
                self.policy,
            )
        except Exception as exc:
            return DeliveryResult("retryable", _safe_error(exc).replace(self.token, "<redacted>"))
        if 200 <= result.status < 300:
            return DeliveryResult("success")
        return DeliveryResult(
            "retryable" if result.status == 429 or result.status >= 500 else "terminal",
            f"HTTP {result.status}",
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
    if telegram_chat_id:
        from .fetch import policy_from_settings

        registry.register(
            TelegramChannel(
                settings.telegram_token,
                telegram_chat_id,
                policy_from_settings(settings, operation="delivery"),
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
    key = (
        idempotency_key
        or hashlib.sha256(
            (url + json.dumps(items, default=_date_handler, sort_keys=True)).encode()
        ).hexdigest()
    )
    channel = WebhookChannel(url=url, timeout=timeout, policy=policy, session=session)
    channel.validate_config()
    for attempt in range(retries):
        results = [channel.send(DeliveryPayload(item, feed or {}, key)) for item in items]
        if all(result.successful for result in results):
            return True
        if any(result.terminal for result in results):
            return False
        if attempt + 1 < retries:
            time.sleep(backoff * (attempt + 1))
    return False


def _safe_error(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(r"(https?://)([^/@\s]+)@", r"\1<redacted>@", text)
    text = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1<redacted>", text)
    text = re.sub(r"(?i)(bot)[0-9]+:[A-Za-z0-9_-]+", r"\1<redacted>", text)
    return text[:1000]

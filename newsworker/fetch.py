"""Transport-neutral, bounded and SSRF-aware outbound HTTP policy."""

from __future__ import annotations

import ipaddress
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union
from urllib.parse import urljoin, urlsplit

import requests

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
SAFE_SCHEMES = {"http", "https"}


class FetchError(RuntimeError):
    """Base error raised by policy-aware transports."""

    code = "fetch_error"


class URLPolicyError(FetchError):
    code = "url_policy"


class AddressPolicyError(URLPolicyError):
    code = "blocked_address"


class RedirectPolicyError(FetchError):
    code = "redirect_policy"


class ResponseTooLarge(FetchError, ValueError):
    code = "response_too_large"


class FetchTimeout(FetchError):
    code = "timeout"


@dataclass(frozen=True)
class FetchRequest:
    url: str
    method: str = "GET"
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Optional[bytes] = None
    operation: str = "source"


@dataclass(frozen=True)
class FetchPolicy:
    timeout: float = 30.0
    max_bytes: int = 10 * 1024 * 1024
    verify_tls: bool = True
    redirect_limit: int = 5
    allowed_hosts: Tuple[str, ...] = ()
    block_private_hosts: bool = True
    allow_private_hosts: bool = False
    trusted_proxy: bool = False
    proxy: Optional[str] = None
    user_agent: str = "newsworker"
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    cookies: Any = None


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    effective_url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    redirect_chain: Tuple[str, ...] = ()
    not_modified: bool = False

    @property
    def validators(self) -> Dict[str, str]:
        return {
            key: value
            for key, value in {
                "etag": self.headers.get("ETag") or self.headers.get("etag"),
                "last_modified": self.headers.get("Last-Modified")
                or self.headers.get("last-modified"),
            }.items()
            if value
        }

    @property
    def content_language(self) -> Optional[str]:
        return self.headers.get("Content-Language") or self.headers.get("content-language")


def _normalize_allowed(hosts: Iterable[str]) -> set[str]:
    return {str(host).rstrip(".").lower() for host in hosts if str(host).strip()}


IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def classify_addresses(host: str) -> Tuple[IPAddress, ...]:
    """Resolve ``host`` and return all unique IP addresses."""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
        return (literal,)
    except ValueError:
        pass
    try:
        records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise URLPolicyError(f"Could not resolve host {host!r}: {exc}") from exc
    addresses = []
    for record in records:
        try:
            address = ipaddress.ip_address(str(record[4][0]).split("%", 1)[0])
        except ValueError:
            continue
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise URLPolicyError(f"Host {host!r} resolved to no usable addresses")
    return tuple(addresses)


def is_unsafe_address(address: IPAddress) -> bool:
    """Return whether an address is local or special-use."""
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def validate_destination(url: str, policy: FetchPolicy) -> str:
    """Validate scheme, credentials, allow-list and every resolved address."""
    parsed = urlsplit(url or "")
    if parsed.scheme.lower() not in SAFE_SCHEMES:
        raise URLPolicyError(
            f"Unsupported URL scheme {parsed.scheme!r} (only http/https are allowed)"
        )
    if not parsed.hostname:
        raise URLPolicyError(f"URL has no host: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise URLPolicyError("Credentials in destination URLs are not allowed")
    host = parsed.hostname.rstrip(".").lower()
    allowed = _normalize_allowed(policy.allowed_hosts)
    if allowed and host not in allowed:
        raise URLPolicyError(f"Host {host!r} is not in the allowed hosts list")

    if policy.block_private_hosts and not policy.trusted_proxy:
        unsafe = [address for address in classify_addresses(host) if is_unsafe_address(address)]
        if unsafe:
            if not (policy.allow_private_hosts and allowed and host in allowed):
                joined = ", ".join(str(address) for address in unsafe)
                raise AddressPolicyError(f"Host {host!r} resolves to blocked address: {joined}")
    return host


def _bounded_body(response: requests.Response, max_bytes: int) -> bytes:
    length = response.headers.get("Content-Length")
    if length:
        try:
            declared = int(length)
        except ValueError:
            declared = None
        if declared is not None and declared > max_bytes:
            raise ResponseTooLarge(f"Response Content-Length {length} exceeds limit {max_bytes}")
    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        size += len(chunk)
        if size > max_bytes:
            raise ResponseTooLarge(f"Response exceeds byte limit {max_bytes}")
        chunks.append(chunk)
    return b"".join(chunks)


class RequestsTransport:
    """Manual-redirect requests adapter enforcing :class:`FetchPolicy`."""

    def __init__(self, session: Optional[requests.Session] = None):
        self._shared_session = session
        self._shared_lock = threading.RLock() if session is not None else None
        self._local = threading.local()

    @property
    def session(self):
        if self._shared_session is not None:
            return self._shared_session
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def fetch(self, request: FetchRequest, policy: FetchPolicy) -> FetchResult:
        if self._shared_lock is not None:
            with self._shared_lock:
                return self._fetch(request, policy)
        return self._fetch(request, policy)

    def _fetch(self, request: FetchRequest, policy: FetchPolicy) -> FetchResult:
        requested_url = request.url
        current_url = requested_url
        method = request.method.upper()
        body = request.body
        chain = []
        headers = dict(policy.extra_headers)
        if not any(key.lower() == "user-agent" for key in headers):
            headers["User-agent"] = policy.user_agent
        headers.update(dict(request.headers))
        proxies = {"http": policy.proxy, "https": policy.proxy} if policy.proxy else None

        for redirect_index in range(policy.redirect_limit + 1):
            validate_destination(current_url, policy)
            try:
                kwargs = {
                    "headers": headers,
                    "timeout": policy.timeout,
                    "verify": policy.verify_tls,
                    "proxies": proxies,
                    "cookies": policy.cookies,
                    "allow_redirects": False,
                    "stream": True,
                }
                if method == "GET":
                    response = self.session.get(current_url, **kwargs)
                else:
                    kwargs["data"] = body
                    response = self.session.request(method, current_url, **kwargs)
            except requests.Timeout as exc:
                raise FetchTimeout(f"Request timed out after {policy.timeout}s") from exc
            except requests.RequestException as exc:
                raise FetchError(str(exc)) from exc

            status_code = getattr(response, "status_code", 200)
            if status_code in REDIRECT_STATUSES and response.headers.get("Location"):
                if redirect_index >= policy.redirect_limit:
                    close = getattr(response, "close", None)
                    if close:
                        close()
                    raise RedirectPolicyError(f"Redirect limit {policy.redirect_limit} exceeded")
                next_url = urljoin(current_url, response.headers["Location"])
                validate_destination(next_url, policy)
                chain.append(next_url)
                if status_code == 303 or (status_code in (301, 302) and method == "POST"):
                    method, body = "GET", None
                close = getattr(response, "close", None)
                if close:
                    close()
                current_url = next_url
                continue

            if status_code == 304:
                close = getattr(response, "close", None)
                if close:
                    close()
                return FetchResult(
                    requested_url=requested_url,
                    effective_url=current_url,
                    status=status_code,
                    headers=dict(response.headers),
                    body=b"",
                    redirect_chain=tuple(chain),
                    not_modified=True,
                )
            try:
                if request.operation != "delivery":
                    response.raise_for_status()
                response_body = _bounded_body(response, policy.max_bytes)
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
            return FetchResult(
                requested_url=requested_url,
                effective_url=current_url,
                status=status_code,
                headers=dict(response.headers),
                body=response_body,
                redirect_chain=tuple(chain),
            )
        raise RedirectPolicyError("Redirect handling exhausted")


def policy_from_settings(settings: Any, *, operation: str = "source") -> FetchPolicy:
    max_bytes = settings.max_content_bytes
    if operation == "delivery":
        max_bytes = min(max_bytes, getattr(settings, "delivery_max_response_bytes", 1024 * 1024))
    return FetchPolicy(
        timeout=settings.request_timeout,
        max_bytes=max_bytes,
        verify_tls=settings.verify_tls,
        redirect_limit=getattr(settings, "redirect_limit", 5),
        allowed_hosts=tuple(getattr(settings, "allowed_hosts", ()) or ()),
        block_private_hosts=getattr(settings, "block_private_hosts", True),
        allow_private_hosts=getattr(settings, "allow_private_hosts", False),
        trusted_proxy=getattr(settings, "trusted_proxy", False),
        proxy=settings.proxy or None,
        user_agent=settings.user_agent,
        extra_headers=dict(settings.extra_headers),
    )

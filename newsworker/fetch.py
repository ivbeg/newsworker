"""Transport-neutral, bounded and SSRF-aware outbound HTTP policy."""

from __future__ import annotations

import contextlib
import contextvars
import email.utils
import ipaddress
import socket
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, Mapping, Optional, Tuple, Union
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util.retry import Retry

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
SAFE_SCHEMES = {"http", "https"}

#: Request headers that must never follow a redirect to another origin.
SENSITIVE_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization", "x-api-key", "x-auth-token"}
)


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


class RateLimited(FetchError):
    """The site asked us to wait longer than the policy allows."""

    code = "rate_limited"


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
    #: Honour HTTP(S)_PROXY / NO_PROXY / .netrc from the environment.
    trust_env: bool = False
    #: Politeness for page fetches (``operation="source"``): at most this many
    #: requests in flight per host (0 = unlimited), at least this many seconds
    #: between request starts (raised to robots.txt ``Crawl-delay``), and the
    #: longest a request may wait for a slot or a ``Retry-After`` window.
    host_concurrency: int = 0
    host_interval: float = 0.0
    max_host_wait: float = 30.0


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


#: Upper bounds for site-provided waits, so a hostile header cannot park a worker.
MAX_CRAWL_DELAY = 60.0
MAX_RETRY_AFTER = 3600.0


@dataclass
class _HostState:
    active: int = 0
    next_start: float = 0.0
    not_before: float = 0.0
    crawl_delay: float = 0.0


class HostScheduler:
    """Per-host request pacing shared by every transport in the process.

    Batch workers, the feed server and full-text fetches each own transports,
    so politeness has to live in one place: a cap on concurrent requests per
    host, a minimum spacing between request starts (``Crawl-delay``), and a
    "not before" time set by ``Retry-After``. Waits are bounded by the policy's
    ``max_host_wait``; longer ones fail fast with :class:`RateLimited`.
    """

    MAX_HOSTS = 4096

    def __init__(self, clock: Callable[[], float] = time.monotonic, sleep=time.sleep):
        self._clock = clock
        self._sleep = sleep
        self._hosts: OrderedDict[str, _HostState] = OrderedDict()
        self._cond = threading.Condition()

    def _state(self, host: str) -> _HostState:
        state = self._hosts.get(host)
        if state is None:
            state = self._hosts[host] = _HostState()
            self._evict()
        self._hosts.move_to_end(host)
        return state

    def _evict(self) -> None:
        if len(self._hosts) <= self.MAX_HOSTS:
            return
        now = self._clock()
        for host in list(self._hosts):
            state = self._hosts[host]
            if state.active == 0 and max(state.next_start, state.not_before) <= now:
                del self._hosts[host]
                if len(self._hosts) <= self.MAX_HOSTS:
                    return

    def clear(self) -> None:
        """Forget all hosts (tests, or a long-lived process that wants a reset)."""
        with self._cond:
            self._hosts.clear()
            self._cond.notify_all()

    def note_crawl_delay(self, host: str, seconds: Optional[float]) -> None:
        with self._cond:
            self._state(host).crawl_delay = min(max(0.0, float(seconds or 0)), MAX_CRAWL_DELAY)

    def note_retry_after(self, host: str, seconds: float) -> None:
        with self._cond:
            state = self._state(host)
            until = self._clock() + min(max(0.0, seconds), MAX_RETRY_AFTER)
            state.not_before = max(state.not_before, until)

    def reserve(self, host: str, *, interval: float = 0.0, max_wait: float = 30.0) -> float:
        """Claim the next start time for ``host``; return how long to wait for it."""
        with self._cond:
            state = self._state(host)
            now = self._clock()
            start = max(now, state.next_start, state.not_before)
            delay = start - now
            if delay > max_wait:
                raise RateLimited(
                    f"{host} asks to wait {delay:.0f}s, more than the {max_wait:.0f}s allowed"
                )
            state.next_start = start + max(interval, state.crawl_delay)
            return delay

    @contextlib.contextmanager
    def slot(self, host: str, policy: FetchPolicy) -> Iterator[None]:
        """Hold one of ``host``'s concurrent slots and start on schedule."""
        with self._cond:
            deadline = self._clock() + policy.max_host_wait
            while (
                policy.host_concurrency > 0 and self._state(host).active >= policy.host_concurrency
            ):
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise RateLimited(
                        f"No free request slot for {host} within {policy.max_host_wait:.0f}s"
                    )
                self._cond.wait(remaining)
            self._state(host).active += 1
        try:
            delay = self.reserve(host, interval=policy.host_interval, max_wait=policy.max_host_wait)
            if delay > 0:
                self._sleep(delay)
            yield
        finally:
            with self._cond:
                self._state(host).active -= 1
                self._cond.notify_all()


#: The process-wide scheduler used by :class:`RequestsTransport` and the
#: aiohttp adapter.
HOSTS = HostScheduler()


def retry_after_seconds(value: Optional[str], now: Optional[float] = None) -> Optional[float]:
    """Parse a ``Retry-After`` header (delta seconds or HTTP date)."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    current = time.time() if now is None else now
    return max(0.0, when.timestamp() - current)


def _paced(request: FetchRequest, host: str, policy: FetchPolicy):
    # Delivery endpoints (webhooks, bot APIs) are not crawled; only pace pages.
    if request.operation != "source":
        return contextlib.nullcontext()
    return HOSTS.slot(host, policy)


# The policy and proxy state of the request being sent on this thread/task. The
# guarded connections below read it when a socket is opened.
_ACTIVE_GUARD: contextvars.ContextVar[Optional[Tuple[FetchPolicy, bool]]] = contextvars.ContextVar(
    "newsworker_active_guard", default=None
)


def check_connected_address(host: str, sock: socket.socket) -> None:
    """Reject a socket whose peer is a blocked address under the active policy.

    The check runs on the address the socket actually connected to, so a DNS
    answer that changes between validation and connection (DNS rebinding)
    cannot reach a private address.
    """
    state = _ACTIVE_GUARD.get()
    if state is None:
        return
    policy, proxied = state
    if proxied or not policy.block_private_hosts or policy.trusted_proxy:
        return
    try:
        peer = sock.getpeername()[0]
        address = ipaddress.ip_address(str(peer).split("%", 1)[0])
    except (OSError, ValueError, IndexError):
        return
    if not is_unsafe_address(address):
        return
    host = (host or "").rstrip(".").lower()
    allowed = _normalize_allowed(policy.allowed_hosts)
    if policy.allow_private_hosts and allowed and host in allowed:
        return
    sock.close()
    raise AddressPolicyError(f"Connection to {host!r} reached blocked address {address}")


class GuardedHTTPConnection(HTTPConnection):
    def _new_conn(self):  # type: ignore[override]
        sock = super()._new_conn()
        check_connected_address(self.host, sock)
        return sock


class GuardedHTTPSConnection(HTTPSConnection):
    def _new_conn(self):  # type: ignore[override]
        sock = super()._new_conn()
        check_connected_address(self.host, sock)
        return sock


class GuardedHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = GuardedHTTPConnection


class GuardedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = GuardedHTTPSConnection


class GuardedHTTPAdapter(HTTPAdapter):
    """Requests adapter whose direct connections enforce the address policy."""

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = {
            "http": GuardedHTTPConnectionPool,
            "https": GuardedHTTPSConnectionPool,
        }


def new_session(retries: Optional[Retry] = None) -> requests.Session:
    """Build a session that checks connected addresses and ignores the environment."""
    session = requests.Session()
    session.trust_env = False
    adapter = GuardedHTTPAdapter(
        max_retries=retries if retries is not None else 0, pool_connections=10, pool_maxsize=20
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _origin(url: str) -> Tuple[str, str, Optional[int]]:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    port = parts.port or {"http": 80, "https": 443}.get(scheme)
    return scheme, (parts.hostname or "").rstrip(".").lower(), port


def strip_cross_origin_headers(
    headers: Dict[str, str], policy: FetchPolicy, *, keep: Iterable[str] = ()
) -> Dict[str, str]:
    """Drop credentials and user-supplied headers before leaving the origin."""
    configured = {key.lower() for key in policy.extra_headers}
    retained = {key.lower() for key in keep}
    return {
        key: value
        for key, value in headers.items()
        if key.lower() in retained
        or (key.lower() not in SENSITIVE_HEADERS and key.lower() not in configured)
    }


class RequestsTransport:
    """Manual-redirect requests adapter enforcing :class:`FetchPolicy`.

    Without an explicit ``session`` every thread gets its own guarded session,
    so concurrent fetches proceed in parallel.  An explicit shared session is
    still supported for compatibility and is serialised with a lock.
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        *,
        session_factory: Optional[Callable[[], requests.Session]] = None,
    ):
        self._shared_session = session
        self._shared_lock = threading.RLock() if session is not None else None
        self._session_factory = session_factory
        self._local = threading.local()

    @property
    def session(self):
        if self._shared_session is not None:
            return self._shared_session
        if self._session_factory is not None:
            return self._session_factory()
        session = getattr(self._local, "session", None)
        if session is None:
            session = new_session()
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
        session = self.session
        if hasattr(session, "trust_env"):
            session.trust_env = policy.trust_env
        start_origin = _origin(requested_url)

        for redirect_index in range(policy.redirect_limit + 1):
            validate_destination(current_url, policy)
            host = (urlsplit(current_url).hostname or "").lower()
            with _paced(request, host, policy):
                proxied = bool(policy.proxy) or bool(
                    policy.trust_env and requests.utils.get_environ_proxies(current_url)
                )
                token = _ACTIVE_GUARD.set((policy, proxied))
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
                        response = session.get(current_url, **kwargs)
                    else:
                        kwargs["data"] = body
                        response = session.request(method, current_url, **kwargs)
                except requests.Timeout as exc:
                    raise FetchTimeout(f"Request timed out after {policy.timeout}s") from exc
                except requests.RequestException as exc:
                    blocked = _find_cause(exc, AddressPolicyError)
                    if blocked is not None:
                        raise blocked from exc
                    raise FetchError(str(exc)) from exc
                finally:
                    _ACTIVE_GUARD.reset(token)

                status_code = getattr(response, "status_code", 200)
                if status_code in (429, 503):
                    wait = retry_after_seconds(response.headers.get("Retry-After"))
                    if wait is not None:
                        HOSTS.note_retry_after(host, wait)
                if status_code in REDIRECT_STATUSES and response.headers.get("Location"):
                    if redirect_index >= policy.redirect_limit:
                        close = getattr(response, "close", None)
                        if close:
                            close()
                        raise RedirectPolicyError(
                            f"Redirect limit {policy.redirect_limit} exceeded"
                        )
                    next_url = urljoin(current_url, response.headers["Location"])
                    validate_destination(next_url, policy)
                    if _origin(next_url) != start_origin:
                        # Credentials belong to the origin they were configured for;
                        # requests' own redirect stripping is bypassed by manual redirects.
                        headers = strip_cross_origin_headers(headers, policy, keep=("User-agent",))
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


def _find_cause(exc: BaseException, kind: type) -> Optional[BaseException]:
    """Find a ``kind`` exception wrapped by requests/urllib3 around ``exc``."""
    seen = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, kind):
            return current
        seen.add(id(current))
        for arg in getattr(current, "args", ()):
            candidates = (arg, getattr(arg, "reason", None))
            for candidate in candidates:
                if isinstance(candidate, BaseException) and isinstance(candidate, kind):
                    return candidate
        current = current.__cause__ or current.__context__
    return None


def policy_from_settings(settings: Any, *, operation: str = "source") -> FetchPolicy:
    """Build the outbound policy for page fetches or for delivery channels.

    Delivery requests never inherit the source ``extra_headers``: those carry
    credentials for the pages being read, not for webhooks or bot APIs.
    """
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
        extra_headers=dict(settings.extra_headers) if operation != "delivery" else {},
        trust_env=bool(getattr(settings, "trust_env_proxy", False)),
        host_concurrency=int(getattr(settings, "per_host_concurrency", 0) or 0),
        host_interval=float(getattr(settings, "per_host_delay", 0.0) or 0.0),
        max_host_wait=float(getattr(settings, "max_host_wait", 30.0)),
    )

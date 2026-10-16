#!/usr/bin/env python
"""Optional aiohttp adapter conforming to the shared fetch policy."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
import urllib.request
from typing import Dict, List, Mapping, Optional, Set, Union
from urllib.parse import urljoin, urlsplit

from .fetch import (
    HOSTS,
    REDIRECT_STATUSES,
    FetchError,
    FetchResult,
    FetchTimeout,
    RedirectPolicyError,
    ResponseTooLarge,
    _origin,
    check_address,
    policy_from_settings,
    retry_after_seconds,
    strip_cross_origin_headers,
    validate_destination,
)


def aiohttp_available() -> bool:
    try:
        import aiohttp  # noqa: F401

        return True
    except ImportError:
        return False


def _ssl_context(verify_tls: bool):
    if verify_tls:
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _proxy_hosts(policy) -> Set[str]:
    """Hosts of the proxies requests may go through; their addresses are not checked."""
    candidates = [policy.proxy] if policy.proxy else []
    if policy.trust_env:
        candidates.extend(urllib.request.getproxies().values())
    hosts = set()
    for candidate in candidates:
        if not candidate:
            continue
        host = urlsplit(candidate if "://" in candidate else f"http://{candidate}").hostname
        if host:
            hosts.add(host.rstrip(".").lower())
    return hosts


def _guarded_resolver(policy):
    """An aiohttp resolver that refuses blocked addresses for the connection itself.

    aiohttp connects to exactly the addresses its resolver returns, so checking
    them here closes the DNS-rebinding window between ``validate_destination``
    and the connection, as the guarded sockets do for the synchronous transport.
    Proxy hosts are exempt: a local proxy is configuration, not a destination.
    """
    from aiohttp.abc import AbstractResolver
    from aiohttp.resolver import DefaultResolver

    exempt = _proxy_hosts(policy)

    class GuardedResolver(AbstractResolver):
        def __init__(self):
            self._inner = DefaultResolver()

        async def resolve(self, host, port=0, family=socket.AF_INET):
            records = await self._inner.resolve(host, port, family)
            if host.rstrip(".").lower() not in exempt:
                for record in records:
                    address = ipaddress.ip_address(str(record["host"]).split("%", 1)[0])
                    check_address(host, address, policy)
            return records

        async def close(self):
            await self._inner.close()

    return GuardedResolver()


def _cookie_jar(cookies):
    """Copy a ``http.cookiejar`` jar into an aiohttp jar, keeping each cookie's domain."""
    from http.cookies import SimpleCookie

    import aiohttp
    from yarl import URL

    jar = aiohttp.CookieJar()
    if cookies is None:
        return jar
    if isinstance(cookies, Mapping):
        # Plain name/value pairs carry no domain; like requests, send them everywhere.
        jar.update_cookies(dict(cookies))
        return jar
    for cookie in cookies:
        domain = (cookie.domain or "").lstrip(".")
        if not domain or cookie.value is None:
            continue
        morsel_set: SimpleCookie = SimpleCookie()
        morsel_set[cookie.name] = cookie.value
        morsel = morsel_set[cookie.name]
        if cookie.domain_specified or cookie.domain.startswith("."):
            morsel["domain"] = domain
        morsel["path"] = cookie.path or "/"
        if cookie.secure:
            morsel["secure"] = True
        scheme = "https" if cookie.secure else "http"
        jar.update_cookies(morsel_set, response_url=URL(f"{scheme}://{domain}/"))
    return jar


class _HostLimits:
    """Per-host concurrency for one async batch; timing comes from ``HOSTS``."""

    def __init__(self, policy):
        self.policy = policy
        self._semaphores = {}

    def semaphore(self, host):
        if self.policy.host_concurrency <= 0:
            return None
        if host not in self._semaphores:
            self._semaphores[host] = asyncio.Semaphore(self.policy.host_concurrency)
        return self._semaphores[host]


async def _fetch_one(session, url, policy, limits=None, request_headers=None):
    limits = limits or _HostLimits(policy)
    requested_url = url
    current_url = url
    chain = []
    headers = dict(policy.extra_headers)
    if not any(key.lower() == "user-agent" for key in headers):
        headers["User-Agent"] = policy.user_agent
    headers.update(dict(request_headers or {}))
    start_origin = _origin(requested_url)
    for redirect_index in range(policy.redirect_limit + 1):
        validate_destination(current_url, policy)
        host = (urlsplit(current_url).hostname or "").lower()
        semaphore = limits.semaphore(host)
        if semaphore is not None:
            await semaphore.acquire()
        try:
            delay = HOSTS.reserve(
                host, interval=policy.host_interval, max_wait=policy.max_host_wait
            )
            if delay > 0:
                await asyncio.sleep(delay)
            outcome = await _send(session, current_url, policy, host, headers)
        finally:
            if semaphore is not None:
                semaphore.release()
        if isinstance(outcome, str):
            if redirect_index >= policy.redirect_limit:
                raise RedirectPolicyError(f"Redirect limit {policy.redirect_limit} exceeded")
            current_url = urljoin(current_url, outcome)
            validate_destination(current_url, policy)
            if _origin(current_url) != start_origin:
                # Credentials belong to the origin they were configured for.
                headers = strip_cross_origin_headers(headers, policy, keep=("User-Agent",))
            chain.append(current_url)
            continue
        status, response_headers, body = outcome
        return FetchResult(
            requested_url,
            current_url,
            status,
            response_headers,
            body,
            tuple(chain),
            status == 304,
        )
    raise RedirectPolicyError("Redirect handling exhausted")


async def _send(session, current_url, policy, host, headers=None):
    """One request: a redirect ``Location`` string or ``(status, headers, body)``."""
    import aiohttp

    try:
        async with session.get(
            current_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=policy.timeout),
            proxy=policy.proxy,
            allow_redirects=False,
        ) as response:
            if response.status in (429, 503):
                wait = retry_after_seconds(response.headers.get("Retry-After"))
                if wait is not None:
                    HOSTS.note_retry_after(host, wait)
            if response.status in REDIRECT_STATUSES and response.headers.get("Location"):
                return response.headers["Location"]
            if response.status == 304:
                return 304, dict(response.headers), b""
            response.raise_for_status()
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > policy.max_bytes:
                raise ResponseTooLarge(
                    f"Response Content-Length {declared} exceeds limit {policy.max_bytes}"
                )
            chunks = []
            total = 0
            async for chunk in response.content.iter_chunked(64 * 1024):
                total += len(chunk)
                if total > policy.max_bytes:
                    raise ResponseTooLarge(f"Response exceeds byte limit {policy.max_bytes}")
                chunks.append(chunk)
            return response.status, dict(response.headers), b"".join(chunks)
    except asyncio.TimeoutError as exc:
        raise FetchTimeout(f"Request timed out after {policy.timeout}s") from exc
    except aiohttp.ClientError as exc:
        raise FetchError(str(exc)) from exc


async def fetch_urls_async(
    urls: List[str],
    *,
    policy=None,
    user_agent: str = "",
    timeout: int = 30,
    verify_tls: bool = True,
    proxy: str = "",
    max_bytes: int = 10 * 1024 * 1024,
    max_concurrency: int = 8,
    extra_headers: Optional[dict] = None,
    request_headers: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> Dict[str, Union[FetchResult, Exception]]:
    """Fetch ``urls`` concurrently under ``policy``.

    ``request_headers`` maps a URL to headers for that request only, such as
    ``If-None-Match`` for a cached copy.
    """
    import aiohttp

    if policy is None:
        from .fetch import FetchPolicy

        policy = FetchPolicy(
            timeout=timeout,
            max_bytes=max_bytes,
            verify_tls=verify_tls,
            proxy=proxy or None,
            user_agent=user_agent or "newsworker",
            extra_headers=dict(extra_headers or {}),
        )
    connector = aiohttp.TCPConnector(
        ssl=_ssl_context(policy.verify_tls), resolver=_guarded_resolver(policy)
    )
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    limits = _HostLimits(policy)
    per_url = request_headers or {}
    results: Dict[str, Union[FetchResult, Exception]] = {}
    async with aiohttp.ClientSession(
        connector=connector,
        cookie_jar=_cookie_jar(policy.cookies),
        trust_env=policy.trust_env,
    ) as session:

        async def worker(url):
            async with semaphore:
                try:
                    results[url] = await _fetch_one(
                        session, url, policy, limits, request_headers=per_url.get(url)
                    )
                except Exception as exc:
                    results[url] = exc

        await asyncio.gather(*(worker(url) for url in urls))
    return results


def fetch_urls_concurrent(urls, settings, max_workers=8, *, policy=None, request_headers=None):
    if not aiohttp_available():
        raise RuntimeError(
            "Async transport requires aiohttp; install with: pip install 'newsworker[async]'"
        )
    return asyncio.run(
        fetch_urls_async(
            list(urls),
            policy=policy or policy_from_settings(settings),
            max_concurrency=max_workers,
            request_headers=request_headers,
        )
    )

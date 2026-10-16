#!/usr/bin/env python
"""Optional aiohttp adapter conforming to the shared fetch policy."""

from __future__ import annotations

import asyncio
import ssl
from typing import Dict, List, Optional, Union
from urllib.parse import urljoin

from .fetch import (
    REDIRECT_STATUSES,
    FetchError,
    FetchResult,
    FetchTimeout,
    RedirectPolicyError,
    ResponseTooLarge,
    policy_from_settings,
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


async def _fetch_one(session, url, policy):
    import aiohttp

    requested_url = url
    current_url = url
    chain = []
    for redirect_index in range(policy.redirect_limit + 1):
        validate_destination(current_url, policy)
        try:
            async with session.get(
                current_url,
                timeout=aiohttp.ClientTimeout(total=policy.timeout),
                proxy=policy.proxy,
                allow_redirects=False,
            ) as response:
                if response.status in REDIRECT_STATUSES and response.headers.get("Location"):
                    if redirect_index >= policy.redirect_limit:
                        raise RedirectPolicyError(
                            f"Redirect limit {policy.redirect_limit} exceeded"
                        )
                    current_url = urljoin(current_url, response.headers["Location"])
                    validate_destination(current_url, policy)
                    chain.append(current_url)
                    continue
                if response.status == 304:
                    return FetchResult(
                        requested_url,
                        current_url,
                        304,
                        dict(response.headers),
                        b"",
                        tuple(chain),
                        True,
                    )
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
                return FetchResult(
                    requested_url,
                    current_url,
                    response.status,
                    dict(response.headers),
                    b"".join(chunks),
                    tuple(chain),
                )
        except asyncio.TimeoutError as exc:
            raise FetchTimeout(f"Request timed out after {policy.timeout}s") from exc
        except aiohttp.ClientError as exc:
            raise FetchError(str(exc)) from exc
    raise RedirectPolicyError("Redirect handling exhausted")


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
) -> Dict[str, Union[FetchResult, Exception]]:
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
    headers = dict(policy.extra_headers)
    headers.setdefault("User-Agent", policy.user_agent)
    connector = aiohttp.TCPConnector(ssl=_ssl_context(policy.verify_tls))
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: Dict[str, Union[FetchResult, Exception]] = {}
    async with aiohttp.ClientSession(
        headers=headers,
        connector=connector,
        cookies=policy.cookies,
    ) as session:

        async def worker(url):
            async with semaphore:
                try:
                    results[url] = await _fetch_one(session, url, policy)
                except Exception as exc:
                    results[url] = exc

        await asyncio.gather(*(worker(url) for url in urls))
    return results


def fetch_urls_concurrent(urls, settings, max_workers=8):
    if not aiohttp_available():
        raise RuntimeError(
            "Async transport requires aiohttp; install with: pip install 'newsworker[async]'"
        )
    return asyncio.run(
        fetch_urls_async(
            list(urls),
            policy=policy_from_settings(settings),
            max_concurrency=max_workers,
        )
    )

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Optional asyncio/aiohttp transport for high-throughput batch fetches."""

import asyncio
import logging
import ssl
from typing import Dict, List, Optional, Union

log = logging.getLogger(__name__)


def aiohttp_available() -> bool:
    try:
        import aiohttp  # noqa: F401

        return True
    except ImportError:
        return False


def _ssl_context(verify_tls: bool):
    if verify_tls:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def _fetch_one(session, url, timeout, max_bytes, proxy=None):
    async with session.get(url, timeout=timeout, proxy=proxy) as resp:
        resp.raise_for_status()
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise ValueError(
                "Response too large: %s bytes declared (max %d)" % (declared, max_bytes)
            )
        chunks = []
        total = 0
        async for chunk in resp.content.iter_chunked(65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("Response exceeded max size of %d bytes" % max_bytes)
            chunks.append(chunk)
        return b"".join(chunks)


async def fetch_urls_async(
    urls: List[str],
    *,
    user_agent: str = "",
    timeout: int = 30,
    verify_tls: bool = True,
    proxy: str = "",
    max_bytes: int = 10 * 1024 * 1024,
    max_concurrency: int = 8,
    extra_headers: Optional[dict] = None,
) -> Dict[str, Union[bytes, Exception]]:
    """Fetches ``urls`` concurrently; values are bytes or the exception raised."""
    import aiohttp

    headers = dict(extra_headers or {})
    if user_agent:
        headers.setdefault("User-agent", user_agent)
    connector = aiohttp.TCPConnector(ssl=_ssl_context(verify_tls))
    proxy_url = proxy or None
    sem = asyncio.Semaphore(max(1, max_concurrency))
    results: Dict[str, Union[bytes, Exception]] = {}

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:

        async def worker(url):
            async with sem:
                try:
                    results[url] = await _fetch_one(
                        session,
                        url,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        max_bytes=max_bytes,
                        proxy=proxy_url,
                    )
                except Exception as e:  # noqa: BLE001
                    results[url] = e

        await asyncio.gather(*(worker(u) for u in urls))

    return results


def fetch_urls_concurrent(urls, settings, max_workers=8):
    """Sync wrapper around :func:`fetch_urls_async`. Raises when aiohttp is missing."""
    if not aiohttp_available():
        raise RuntimeError(
            "Async transport requires aiohttp; install with: pip install 'newsworker[async]'"
        )
    return asyncio.run(
        fetch_urls_async(
            list(urls),
            user_agent=settings.user_agent,
            timeout=settings.request_timeout,
            verify_tls=settings.verify_tls,
            proxy=settings.proxy,
            max_bytes=settings.max_content_bytes,
            max_concurrency=max_workers,
            extra_headers=settings.extra_headers,
        )
    )

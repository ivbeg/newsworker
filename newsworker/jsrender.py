"""Optional Playwright renderer with strict lifetime and resource bounds."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

from .fetch import FetchPolicy, validate_destination
from .plugins import BaseExtractorPlugin


class BrowserUnavailable(RuntimeError):
    pass


class BrowserRenderError(RuntimeError):
    pass


class BrowserRenderTimeout(BrowserRenderError, TimeoutError):
    pass


@dataclass(frozen=True)
class RenderResult:
    body: bytes
    effective_url: str
    elapsed_ms: float
    wait_condition: str = "domcontentloaded"


class PlaywrightRenderer:
    """One-shot renderer; Playwright remains an optional installation extra."""

    def __init__(
        self,
        policy: FetchPolicy,
        *,
        timeout: int = 15,
        max_bytes: int = 10 * 1024 * 1024,
        concurrency: int = 1,
    ):
        self.policy = policy
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._semaphore = threading.BoundedSemaphore(max(1, concurrency))

    def render(self, url: str) -> RenderResult:
        if not self._semaphore.acquire(timeout=self.timeout):
            raise TimeoutError("browser renderer concurrency limit is saturated")
        try:
            return asyncio.run(self._render(url))
        finally:
            self._semaphore.release()

    async def _render(self, url: str) -> RenderResult:
        validate_destination(url, self.policy)
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise BrowserUnavailable(
                "JavaScript rendering requires: pip install 'newsworker[browser]' "
                "and playwright install chromium"
            ) from exc
        loop = asyncio.get_running_loop()
        started = loop.time()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context(service_workers="block")
            page = await context.new_page()
            navigation_redirects = 0

            async def route_handler(route):
                nonlocal navigation_redirects
                resource_type = route.request.resource_type
                if resource_type in {"media", "font"}:
                    await route.abort()
                    return
                try:
                    validate_destination(route.request.url, self.policy)
                except Exception:
                    await route.abort()
                    return
                is_navigation = getattr(route.request, "is_navigation_request", None)
                if (
                    callable(is_navigation)
                    and is_navigation()
                    and getattr(route.request, "redirected_from", None)
                ):
                    navigation_redirects += 1
                    if navigation_redirects > self.policy.redirect_limit:
                        await route.abort()
                        return
                await route.continue_()

            await page.route("**/*", route_handler)
            try:
                try:
                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout * 1000,
                    )
                except Exception as exc:
                    if (
                        isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                        or type(exc).__name__ == "TimeoutError"
                    ):
                        raise BrowserRenderTimeout(
                            f"browser rendering timed out after {self.timeout}s"
                        ) from exc
                    raise BrowserRenderError(
                        f"browser rendering failed: {type(exc).__name__}"
                    ) from exc
                validate_destination(page.url, self.policy)
                html = (await page.content()).encode("utf-8")
                if len(html) > self.max_bytes:
                    raise ValueError(f"rendered document exceeds {self.max_bytes} bytes")
                return RenderResult(
                    body=html,
                    effective_url=page.url,
                    elapsed_ms=(loop.time() - started) * 1000,
                )
            finally:
                await context.close()
                await browser.close()


class PlaywrightExtractorPlugin(BaseExtractorPlugin):
    """Experimental extractor plugin usable through ``newsworker.extractors``."""

    def __init__(self, renderer: PlaywrightRenderer, *, enabled=True):
        self.renderer = renderer
        self.enabled = enabled

    def matches(self, url: str) -> bool:
        return self.enabled

    def extract(self, url: str, data=None, **kwargs):
        from .extractor import FeedExtractor

        result = self.renderer.render(url)
        feed, _session = FeedExtractor().get_feed(
            result.effective_url,
            data=result.body,
            user_agent=kwargs.get("user_agent"),
        )
        feed.setdefault("provenance", {})["strategy"] = "browser"
        return feed

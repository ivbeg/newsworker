#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
High level feed service combining caching with extraction.

:class:`FeedService` is the shared building block used by both the ``extract``
CLI command and the local HTTP server. It ties together:

* :class:`newsworker.cache.ContentCache` -- avoids re-fetching a page while its
  cached copy is fresh;
* :class:`newsworker.cache.SpecCache` -- reuses a previously built parsing spec,
  building one dynamically on the first request for a URL;
* extraction -- applies the spec with :class:`newsworker.spec.SpecExtractor`, or
  falls back to the fully dynamic :class:`newsworker.extractor.FeedExtractor`
  when no usable spec could be produced.

Cached page content is threaded through the ``data=`` parameter of both
extractors so a single fetch serves both spec building and extraction.
"""

import logging

from .cache import ContentCache, SpecCache
from .extractor import FeedExtractor
from .settings import Settings
from .spec import SpecAnalyzer, SpecExtractor

log = logging.getLogger(__name__)


class FeedService:
    """Builds feeds from URLs with spec and content caching."""

    def __init__(self, settings=None, use_cache=True):
        self.settings = settings or Settings()
        self.use_cache = use_cache
        cache_dir = self.settings.resolved_cache_dir()
        self.content_cache = ContentCache(cache_dir, ttl=self.settings.content_ttl)
        self.spec_cache = SpecCache(cache_dir, ttl=self.settings.spec_ttl)
        self.extractor = FeedExtractor(
            filtered_text_length=self.settings.filtered_text_length
        )

    def _fetch(self, url, force_refresh=False):
        """Returns page bytes, honoring the content cache unless refreshing."""
        if self.use_cache and not force_refresh:
            cached = self.content_cache.get(url)
            if cached is not None:
                log.debug("Content cache hit for %s", url)
                return cached
        data = self.extractor.fetch(url, self.settings.user_agent)
        if self.use_cache:
            try:
                self.content_cache.set(url, data)
            except OSError as e:
                log.warning("Failed to cache content for %s: %s", url, e)
        return data

    def _get_or_build_spec(self, url, data):
        """Returns a cached spec, or builds and caches one dynamically."""
        if self.use_cache:
            spec = self.spec_cache.get(url)
            if spec is not None:
                log.debug("Spec cache hit for %s", url)
                return spec
        analyzer = SpecAnalyzer(
            filtered_text_length=self.settings.filtered_text_length
        )
        spec = analyzer.analyze(url, data=data, user_agent=self.settings.user_agent)
        if self.use_cache and spec is not None and spec.fields:
            try:
                self.spec_cache.set(url, spec)
                log.debug("Spec cached for %s", url)
            except OSError as e:
                log.warning("Failed to cache spec for %s: %s", url, e)
        return spec

    def get_feed(self, url, force_refresh=False, explicit_spec=None):
        """Returns the internal feed dictionary for ``url``.

        :param force_refresh: bypass the content cache and re-fetch the page.
        :param explicit_spec: use this :class:`FeedSpec` instead of the cache.
        """
        data = self._fetch(url, force_refresh=force_refresh)

        spec = explicit_spec
        if spec is None:
            spec = self._get_or_build_spec(url, data)

        if spec is not None and spec.fields:
            return SpecExtractor(extractor=self.extractor).extract(
                url, spec, data=data, user_agent=self.settings.user_agent
            )

        log.debug("No usable spec for %s, using dynamic extraction", url)
        feed, _session = self.extractor.get_feed(
            url, data=data, user_agent=self.settings.user_agent
        )
        return feed

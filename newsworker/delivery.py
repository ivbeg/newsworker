#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Webhook delivery of new feed items."""

import logging
import time

import requests

from .formats import _date_handler
from .tools import validate_url

log = logging.getLogger(__name__)


def deliver_webhook(url, items, feed=None, retries=3, backoff=1.0, timeout=30, session=None):
    """POSTs ``items`` as JSON to ``url`` with retry/backoff.

    The payload is ``{"feed": {...}, "items": [...]}``. The target URL is
    validated (http/https only) before any request. Returns ``True`` on a 2xx
    response, ``False`` when all attempts fail. Raises ``ValueError`` for an
    invalid URL.
    """
    validate_url(url)
    if not items:
        return True
    http = session or requests
    payload = {
        "feed": {
            "title": (feed or {}).get("title"),
            "link": (feed or {}).get("link"),
        },
        "items": items,
    }
    # Reuse the feed date handler so datetimes serialize as ISO strings.
    import json

    body = json.dumps(payload, default=_date_handler, ensure_ascii=False).encode("utf-8")
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = http.post(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            if 200 <= resp.status_code < 300:
                return True
            last_error = "HTTP %s" % resp.status_code
        except requests.exceptions.RequestException as e:
            last_error = str(e)
        if attempt < retries:
            time.sleep(backoff * attempt)
    log.warning("Webhook delivery to %s failed after %d attempts: %s", url, retries, last_error)
    return False

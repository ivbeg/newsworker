"""Every strategy returns the shape declared in ``newsworker.model``."""

import datetime as dt
import typing

from newsworker.model import Feed, Item
from newsworker.native import parse_native_feed
from newsworker.service import FeedService
from newsworker.settings import Settings

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title><link href="https://ex.org/"/>
<id>urn:t</id><updated>2026-10-15T10:00:00Z</updated>
<entry><title>One</title><id>urn:1</id><link href="https://ex.org/1"/>
<updated>2026-10-15T10:00:00Z</updated><summary>s</summary></entry></feed>"""

PAGE = (
    "<html><body><ul>"
    + "".join(
        f'<li><a href="/n/{i}">Headline number {i} for the model test</a> '
        f"<span>{day} October 2026</span></li>"
        for i, day in enumerate((15, 12, 9, 5), start=1)
    )
    + "</ul></body></html>"
).encode()

FEED_KEYS = set(typing.get_type_hints(Feed))
ITEM_KEYS = set(typing.get_type_hints(Item))
REQUIRED_FEED = {"title", "link", "description", "language", "items"}
REQUIRED_ITEM = {"title", "description", "pubdate", "link", "unique_id"}


def _check(feed):
    assert REQUIRED_FEED <= set(feed) <= FEED_KEYS, set(feed) - FEED_KEYS
    assert feed["items"]
    for item in feed["items"]:
        assert REQUIRED_ITEM <= set(item) <= ITEM_KEYS, set(item) - ITEM_KEYS
        pubdate = item["pubdate"]
        assert pubdate is None or (
            isinstance(pubdate, dt.datetime) and pubdate.utcoffset() == dt.timedelta(0)
        )


def test_native_feed_matches_the_model():
    _check(parse_native_feed(ATOM, "https://ex.org/feed"))


def test_html_extraction_matches_the_model(tmp_path):
    service = FeedService(Settings(cache_dir=str(tmp_path)), plugins=[], bridges=[])
    _check(service.get_feed("https://ex.org/news", data=PAGE))

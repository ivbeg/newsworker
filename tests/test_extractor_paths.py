"""Less common page shapes and the fetch helpers of the dynamic extractor."""

import datetime as dt

import pytest

from newsworker.extractor import FeedExtractor
from newsworker.fetch import HOSTS, FetchResult, FetchTimeout

BASE = "https://example.com/news"
TITLES = [
    "Parliament approves the new budget for next year",
    "Central bank keeps the key rate unchanged again",
    "City opens a new library in the old station building",
    "National team wins the regional championship final",
]


def _feed(html):
    feed, _session = FeedExtractor(filtered_text_length=150).get_feed(BASE, data=html.encode())
    return feed


def _titles(feed):
    return [item["title"] for item in feed["items"]]


def test_table_rows_inside_tbody_become_items():
    rows = "".join(
        f'<tr><td>{day}.10.2026</td><td><a href="/n/{i}">{title}</a></td></tr>'
        for i, (day, title) in enumerate(zip((15, 12, 9, 5), TITLES, strict=True))
    )
    feed = _feed(f"<html><body><table><tbody>{rows}</tbody></table></body></html>")
    assert _titles(feed) == TITLES
    assert feed["items"][0]["link"] == "https://example.com/n/0"
    assert feed["items"][0]["pubdate"] == dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)


def test_date_written_after_an_empty_marker_element():
    # The date is the tail of an empty <i> icon, not the text of an element.
    items = "".join(
        f'<li><i class="icon"></i>{day} October 2026 <a href="/n/{i}">{title}</a></li>'
        for i, (day, title) in enumerate(zip((15, 12, 9, 5), TITLES, strict=True))
    )
    feed = _feed(f"<html><body><ul>{items}</ul></body></html>")
    assert len(feed["items"]) == 4
    assert feed["items"][1]["pubdate"] == dt.datetime(2026, 10, 12, tzinfo=dt.timezone.utc)


def test_html_comments_inside_items_are_ignored():
    items = "".join(
        f'<div class="post"><!-- teaser --><h3><a href="/n/{i}">{title}</a></h3>'
        f"<!-- date --><span>{day} October 2026</span></div>"
        for i, (day, title) in enumerate(zip((15, 12, 9, 5), TITLES, strict=True))
    )
    feed = _feed(f"<html><body><main>{items}</main></body></html>")
    assert _titles(feed) == TITLES


def test_text_after_a_link_is_used_as_description():
    items = "".join(
        f'<p><span>{day} October 2026</span> <a href="/n/{i}">{title}</a> '
        "Short teaser text that follows the headline link.</p>"
        for i, (day, title) in enumerate(zip((15, 12, 9, 5), TITLES, strict=True))
    )
    feed = _feed(f"<html><body><div>{items}</div></body></html>")
    assert _titles(feed) == TITLES
    assert "teaser text" in feed["items"][0]["description"]


def test_unparseable_page_gives_an_empty_feed_named_after_the_url():
    feed, session = FeedExtractor().get_feed(BASE, data=b"")
    assert feed["items"] == []
    assert feed["title"] == "News from " + BASE
    assert session["log"]


def test_cached_date_patterns_narrow_the_parser_and_are_released():
    html = "".join(
        f'<li><a href="/n/{i}">{title}</a> <span>{day}.10.2026</span></li>'
        for i, (day, title) in enumerate(zip((15, 12, 9, 5), TITLES, strict=True))
    )
    extractor = FeedExtractor()
    feed, _ = extractor.get_feed(BASE, data=f"<ul>{html}</ul>".encode())
    patterns = feed["cache"]["pats"]
    assert patterns
    again, _ = extractor.get_feed(BASE, data=f"<ul>{html}</ul>".encode(), cached_p=patterns)
    assert _titles(again) == _titles(feed)
    # The narrowed session ended: other date formats match again afterwards.
    with extractor.activate_context(extractor._context()):
        assert extractor.match_text("15 October 2026")[0] is True


def test_cookie_file_is_loaded_once_and_bad_files_are_ignored(tmp_path):
    jar_file = tmp_path / "cookies.txt"
    jar_file.write_text(
        "# Netscape HTTP Cookie File\n"
        "example.com\tFALSE\t/\tFALSE\t2147483647\tsession\tabc\n"
    )
    extractor = FeedExtractor(cookies_file=str(jar_file))
    jar = extractor._load_cookies()
    assert [cookie.name for cookie in jar] == ["session"]
    assert extractor._load_cookies() is jar
    broken = tmp_path / "broken.txt"
    broken.write_text("not a cookie file")
    assert list(FeedExtractor(cookies_file=str(broken))._load_cookies()) == []
    assert FeedExtractor()._load_cookies() is None


class _Transport:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    def fetch(self, request, policy):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def _extractor(transport):
    extractor = FeedExtractor(respect_robots=False)
    extractor.transport = transport
    return extractor


def test_conditional_fetch_sends_validators_and_returns_none_when_unchanged():
    unchanged = FetchResult(BASE, BASE, 304, {"ETag": '"v2"'}, b"", (), True)
    transport = _Transport(unchanged)
    extractor = _extractor(transport)
    data = extractor.fetch(
        BASE, conditional={"etag": '"v1"', "last_modified": "Thu, 15 Oct 2026 10:00:00 GMT"}
    )
    assert data is None
    headers = transport.requests[0].headers
    assert headers == {
        "If-None-Match": '"v1"',
        "If-Modified-Since": "Thu, 15 Oct 2026 10:00:00 GMT",
    }
    assert extractor.last_response_meta["etag"] == '"v2"'


def test_fetch_records_page_length_and_logs_timeouts():
    page = FetchResult(BASE, BASE, 200, {"Content-Language": "de-DE"}, b"<html></html>")
    extractor = _extractor(_Transport(page))
    extractor.init_session()
    assert extractor.fetch(BASE) == b"<html></html>"
    assert extractor.session["debug"]["page_length"] == 13
    assert extractor._last_content_language == "de"

    slow = _extractor(_Transport(error=FetchTimeout("too slow")))
    with pytest.raises(FetchTimeout):
        slow.fetch(BASE)
    assert any("Timeout" in str(entry) for entry in slow.log.getlogs())


def test_robots_rules_set_pacing_and_unreadable_robots_allow_fetching():
    HOSTS.clear()
    robots = b"User-agent: *\nRequest-rate: 1/5\nDisallow: /private\n"
    extractor = _extractor(_Transport(FetchResult(BASE, BASE, 200, {}, robots)))
    assert extractor._can_fetch_policy("https://paced.example/news", "bot") is True
    assert extractor._can_fetch_policy("https://paced.example/private/x", "bot") is False
    assert HOSTS._state("paced.example").crawl_delay == 5.0

    broken = _extractor(_Transport(error=OSError("unreachable")))
    assert broken._can_fetch_policy("https://down.example/news", "bot") is True
    HOSTS.clear()

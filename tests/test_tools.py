import datetime

import pytest
from lxml.html import fromstring

from newsworker.tools import (
    Logger,
    can_fetch,
    clean_url,
    clean_urlquery,
    clear_robots_cache,
    decode_html,
    detect_page_language_metadata,
    detect_text_language,
    detect_text_language_from_samples,
    find_next_link,
    get_abs_url,
    normalize_datetime,
    robots_crawl_delay,
    validate_url,
)

# UTF-8 Russian news page (meta charset must be honored; byte-sniffing alone
# misdetects Cyrillic as macroman).
_CYRILLIC_NEWS_HTML = b"""<!doctype html>
<html lang="ru-RU">
<head>
\t<meta charset="UTF-8">
\t<title>\xd0\x9d\xd0\xbe\xd0\xb2\xd0\xbe\xd1\x81\xd1\x82\xd0\xb8</title>
</head>
<body><h1>\xd0\x9d\xd0\xbe\xd0\xb2\xd0\xbe\xd1\x81\xd1\x82\xd0\xb8</h1></body>
</html>"""


def test_clean_url_strips_tracking_params():
    url = "https://example.com/a?utm_source=news&id=5&utm_campaign=x"
    cleaned = clean_url(url)
    assert "utm_source" not in cleaned
    assert "utm_campaign" not in cleaned
    assert "id=5" in cleaned


def test_clean_url_removes_jsessionid():
    url = "https://example.com/page;jsessionid=" + "a" * 32 + "?id=1"
    cleaned = clean_url(url)
    assert "jsessionid" not in cleaned


def test_clean_url_no_query_unchanged():
    url = "https://example.com/plain"
    assert clean_url(url) == url


def test_clean_urlquery_partitions_keys():
    query, kept, filtered = clean_urlquery("id=1&utm_medium=email&page=2")
    assert "id" in kept and "page" in kept
    assert "utm_medium" in filtered


def test_get_abs_url_root_relative_preserves_scheme():
    base = "https://example.com/section/page"
    # Must preserve https (the old implementation downgraded to http).
    assert get_abs_url(base, "/news/1") == "https://example.com/news/1"


def test_get_abs_url_document_relative():
    base = "https://example.com/section/page"
    assert get_abs_url(base, "sibling") == "https://example.com/section/sibling"


def test_get_abs_url_parent_relative():
    base = "https://example.com/a/b/page"
    assert get_abs_url(base, "../other") == "https://example.com/a/other"


def test_get_abs_url_keeps_absolute_url():
    base = "https://example.com/section/page"
    target = "https://other.com/x"
    assert get_abs_url(base, target) == target


def test_get_abs_url_scheme_less_base():
    assert get_abs_url("example.com/news", "/1") == "http://example.com/1"


def test_decode_html_honors_utf8_meta_charset():
    """Regression: Cyrillic UTF-8 pages must not be misread as macroman."""
    decoded = decode_html(_CYRILLIC_NEWS_HTML)
    assert "Новости" in decoded
    assert "–ù–æ–²–æ" not in decoded


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Αυτή είναι μια σημαντική ελληνική είδηση σήμερα", "el"),
        ("هذه أخبار عربية مهمة للغاية اليوم", "ar"),
        ("אלה חדשות חשובות מאוד בעברית היום", "he"),
        ("นี่คือข่าวภาษาไทยที่สำคัญมากวันนี้", "th"),
        ("यह आज की एक बहुत महत्वपूर्ण हिंदी खबर है", "hi"),
        ("오늘 매우 중요한 한국어 뉴스입니다", "ko"),
        ("これは今日のとても重要な日本語ニュースです", "ja"),
        ("这是今天非常重要的中文新闻报道", "zh"),
        ("Eine äußerst wichtige Meldung über größere Änderungen", "de"),
    ],
)
def test_script_and_latin_language_detection_matrix(text, language):
    assert detect_text_language(text) == language


def test_language_and_metadata_empty_error_branches():
    assert detect_text_language("   ") is None
    assert detect_text_language("short") is None
    assert detect_text_language_from_samples([]) is None
    assert detect_page_language_metadata(None) is None

    class BrokenDocument:
        def xpath(self, query):
            raise RuntimeError("broken")

    assert detect_page_language_metadata(BrokenDocument()) is None


def test_datetime_url_pagination_and_logger_edge_cases():
    assert normalize_datetime(None) is None
    with pytest.raises(TypeError):
        normalize_datetime("not-a-date")
    local = datetime.datetime(2026, 1, 1, 12)
    assert normalize_datetime(local, "Europe/Moscow").hour == 9
    assert find_next_link(None, "https://example.com") is None
    doc = fromstring("<html><body><a class='pagination-next' href='/2'>More</a></body></html>")
    assert find_next_link(doc, "https://example.com/1") == "https://example.com/2"
    assert get_abs_url("", "/one") == "/one"
    with pytest.raises(ValueError):
        validate_url("file:///tmp/a")
    with pytest.raises(ValueError):
        validate_url("http:///missing")
    with pytest.raises(ValueError):
        validate_url("https://bad.example", allowed_hosts=["good.example"])
    assert validate_url("https://good.example", allowed_hosts=["good.example"])
    assert clean_url("https://example.com/?utm_source=x") == "https://example.com/"

    logger = Logger(autostart=False)
    logger.reset()
    logger.save("code", "message", autoreset=False)
    assert logger.getlogs()[0]["code"] == "code"
    logger.clear()
    assert logger.getlogs() == []


def test_robots_helpers_cache_leniency_and_delay(monkeypatch):
    clear_robots_cache()
    fetched = []

    def fetch(url):
        fetched.append(url)
        return b"User-agent: *\nDisallow: /blocked\nCrawl-delay: 2\n"

    monkeypatch.setattr("newsworker.tools._default_robots_fetch", fetch)
    assert can_fetch("file:///tmp/a")
    assert can_fetch("https://example.com/open")
    assert not can_fetch("https://example.com/blocked")
    assert robots_crawl_delay("https://example.com/open") == 2.0
    assert fetched == ["https://example.com/robots.txt"]
    assert robots_crawl_delay("file:///tmp/a") is None

    clear_robots_cache()

    def broken(url):
        raise OSError("network")

    monkeypatch.setattr("newsworker.tools._default_robots_fetch", broken)
    assert can_fetch("https://broken.example/path")
    assert robots_crawl_delay("https://broken.example/path") is None

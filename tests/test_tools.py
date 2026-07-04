from newsworker.tools import clean_url, clean_urlquery, get_abs_url


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

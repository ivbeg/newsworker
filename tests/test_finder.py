from lxml import etree
from lxml.html import fromstring

from newsworker.finder import FeedsFinder


def _parse(html_bytes):
    parser = etree.HTMLParser(remove_blank_text=True)
    return fromstring(html_bytes, parser=parser)


def test_collect_feeds_finds_autodiscovery_links(news_list_html):
    root = _parse(news_list_html)
    finder = FeedsFinder()
    feeds = finder.collect_feeds(root, "https://example.com/")
    urls = {f["url"] for f in feeds}
    assert "https://example.com/feed.xml" in urls
    assert "https://example.com/atom.xml" in urls


def test_collect_feeds_records_feedtypes(news_list_html):
    root = _parse(news_list_html)
    finder = FeedsFinder()
    feeds = finder.collect_feeds(root, "https://example.com/")
    by_url = {f["url"]: f for f in feeds}
    assert by_url["https://example.com/feed.xml"]["feedtype"] == "rss"
    assert by_url["https://example.com/atom.xml"]["feedtype"] == "atom"


def test_collect_feeds_deduplicates(news_list_html):
    root = _parse(news_list_html)
    finder = FeedsFinder()
    feeds = finder.collect_feeds(root, "https://example.com/")
    urls = [f["url"] for f in feeds]
    assert len(urls) == len(set(urls))

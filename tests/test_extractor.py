import datetime

from newsworker.extractor import FeedExtractor


def test_get_feed_extracts_items_offline(news_list_html):
    ext = FeedExtractor(filtered_text_length=150)
    feed, session = ext.get_feed("https://example.com/news", data=news_list_html)
    assert feed["title"] == "Example News Portal"
    assert len(feed["items"]) == 4


def test_items_have_dates_and_titles(news_list_html):
    ext = FeedExtractor(filtered_text_length=150)
    feed, _ = ext.get_feed("https://example.com/news", data=news_list_html)
    for item in feed["items"]:
        assert isinstance(item["pubdate"], datetime.datetime)
        assert item["title"]


def test_links_are_populated_regression(news_list_html):
    """Regression test for the process_clusters indentation bug.

    Link/image/date detection used to run outside the annotation loop (and only
    when a description was assembled), so items lost their links and were often
    dropped entirely. Every item must now carry its own resolved link.
    """
    ext = FeedExtractor(filtered_text_length=150)
    feed, _ = ext.get_feed("https://example.com/news", data=news_list_html)
    links = [item["link"] for item in feed["items"]]
    assert all(link and link.startswith("http") for link in links)
    # Links should be distinct per item, not a single shared/base URL.
    assert len(set(links)) == len(feed["items"])
    # Scheme is preserved from the base URL (https), not downgraded to http.
    assert "https://example.com/news/first-story" in links


def test_cached_patterns_exposed(news_list_html):
    ext = FeedExtractor(filtered_text_length=150)
    feed, _ = ext.get_feed("https://example.com/news", data=news_list_html)
    assert feed["cache"]["pats"], "discovered date patterns should be cached"


def test_card_layout_extracts_images(news_cards_html):
    ext = FeedExtractor(filtered_text_length=150)
    feed, _ = ext.get_feed("https://example.com/cards", data=news_cards_html)
    assert len(feed["items"]) == 3
    for item in feed["items"]:
        images = item["extra"]["images"]
        assert images and images[0].startswith("https://example.com/img/")
        assert item["link"].startswith("https://example.com/story/")


def test_learn_feed_delegates_to_get_feed(news_list_html):
    ext = FeedExtractor(filtered_text_length=150)
    feed, session = ext.learn_feed("https://example.com/news", data=news_list_html)
    assert len(feed["items"]) == 4
    assert session is not None

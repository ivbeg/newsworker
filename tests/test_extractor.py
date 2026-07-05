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


def test_wordpress_time_datetime_extracts_items():
    html = (
        "<!DOCTYPE html><html lang=\"es\"><head><title>Noticias</title></head><body>"
        "<main>"
        "<article><time class=\"entry-date\" datetime=\"2026-07-04T20:30:32-03:00\">"
        "4 julio, 2026</time>"
        "<div class=\"archive-meta\">CATEGORÍA EJEMPLO |</div>"
        "<h2 class=\"archive-title\"><a href=\"/story-a\">"
        "Primera noticia importante del ministerio de salud</a></h2>"
        "<p>Resumen de la primera noticia publicada hoy en el portal.</p>"
        "</article>"
        "<article><time class=\"entry-date\" datetime=\"2026-07-03T17:11:02-03:00\">"
        "3 julio, 2026</time>"
        "<h2><a href=\"/story-b\">Segunda noticia sobre salud pública provincial</a></h2>"
        "<p>Resumen de la segunda noticia publicada ayer en el portal.</p>"
        "</article>"
        "<article><time class=\"entry-date\" datetime=\"2026-07-02T16:58:12-03:00\">"
        "2 julio, 2026</time>"
        "<h2><a href=\"/story-c\">Tercera noticia de vacunación en Tucumán</a></h2>"
        "<p>Resumen de la tercera noticia publicada recientemente en el portal.</p>"
        "</article>"
        "</main></body></html>"
    ).encode("utf-8")
    ext = FeedExtractor(filtered_text_length=150)
    feed, _ = ext.get_feed("https://msptucuman.gov.ar/category/noticias/", data=html)
    assert len(feed["items"]) == 3
    assert "CATEGORÍA EJEMPLO" not in feed["items"][0]["title"]
    assert "Primera noticia importante" in feed["items"][0]["title"]
    assert all(item["title"] for item in feed["items"])
    assert feed["items"][0]["pubdate"] == datetime.datetime(2026, 7, 4, 20, 30, 32)

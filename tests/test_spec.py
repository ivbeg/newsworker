import pytest
from lxml.html import fromstring

from newsworker.spec import (
    FeedSpec,
    FieldRule,
    ItemsRule,
    SpecAnalysisError,
    SpecAnalyzer,
    SpecExtractor,
    relative_selector,
    relative_xpath,
)


def _build_manual_spec():
    return FeedSpec(
        source_url="https://example.com/news",
        title="Example News Portal",
        language="en",
        items=ItemsRule(
            selector="li.news-item",
            selector_type="css",
            container="/html/body/main/ul",
        ),
        fields={
            "date": FieldRule(
                selector="span.date",
                source="text",
                patterns=["dt:date:date_9"],
                required=True,
            ),
            "title": FieldRule(selector="a", source="text"),
            "description": FieldRule(selector="p", source="text"),
            "link": FieldRule(selector="a", source="attr:href", absolute=True),
        },
    )


def test_spec_yaml_roundtrip():
    spec = _build_manual_spec()
    reloaded = FeedSpec.from_yaml(spec.to_yaml())
    assert reloaded.title == spec.title
    assert reloaded.items.selector == "li.news-item"
    assert reloaded.fields["date"].required is True
    assert reloaded.fields["date"].patterns == ["dt:date:date_9"]
    assert reloaded.fields["link"].absolute is True


def test_spec_save_load_file(tmp_path):
    spec = _build_manual_spec()
    path = str(tmp_path / "spec.yaml")
    spec.save(path)
    loaded = FeedSpec.load(path)
    assert loaded.items.container == "/html/body/main/ul"
    assert set(loaded.fields) == {"date", "title", "description", "link"}


def test_analyzer_builds_usable_spec(news_list_html):
    spec = SpecAnalyzer(filtered_text_length=150).analyze(
        "https://example.com/news", data=news_list_html
    )
    assert spec.title == "Example News Portal"
    assert "date" in spec.fields
    assert spec.fields["date"].patterns  # discovered date patterns present


def test_analyzer_returns_empty_spec_without_require_items():
    html = b"""<!DOCTYPE html><html><head><title>About</title></head>
    <body><h1>About Us</h1><p>No news here.</p></body></html>"""
    spec = SpecAnalyzer(filtered_text_length=150).analyze(
        "https://example.com/about", data=html
    )
    assert spec.title == "About"
    assert spec.fields == {}


def test_analyzer_raises_when_no_news_items():
    html = b"""<!DOCTYPE html><html><head><title>About</title></head>
    <body><h1>About Us</h1><p>No news here.</p></body></html>"""
    analyzer = SpecAnalyzer(filtered_text_length=150)
    with pytest.raises(SpecAnalysisError, match="No dated news listings"):
        analyzer.analyze("https://example.com/about", data=html, require_items=True)


def test_spec_extractor_offline(news_list_html):
    spec = _build_manual_spec()
    feed = SpecExtractor().extract(
        "https://example.com/news", spec, data=news_list_html
    )
    assert len(feed["items"]) == 4
    first = feed["items"][0]
    assert first["pubdate"] is not None
    assert first["title"] == "First important story about the economy"
    assert first["link"] == "https://example.com/news/first-story"


def test_spec_extractor_respects_required_date(news_list_html):
    spec = _build_manual_spec()
    # Point the date selector at something that never matches a date so the
    # required-date rule drops every item.
    spec.fields["date"].selector = "a"
    feed = SpecExtractor().extract(
        "https://example.com/news", spec, data=news_list_html
    )
    assert feed["items"] == []


def test_relative_xpath_uses_same_tag_index():
    html = """
    <div class="item">
      <div class="item-title">
        <div class="item-date">03.07.2026</div>
        <a href="/story">Story headline here</a>
      </div>
    </div>
    """
    root = fromstring(html)
    title = root.cssselect("div.item-title a")[0]
    xpath = relative_xpath(root, title)
    assert xpath == "./div[1]/a[1]"
    assert root.xpath(xpath)[0].text.strip() == "Story headline here"


def test_relative_selector_prefers_parent_qualified_css():
    html = """
    <div class="item">
      <a href="/noise"></a>
      <div class="item-title">
        <div class="item-date">03.07.2026</div>
        <a href="/story">Story headline here</a>
      </div>
      <a href="/read-more">read more</a>
    </div>
    """
    root = fromstring(html)
    title = root.cssselect("div.item-title a")[0]
    selector = relative_selector(root, title)
    assert selector == "div.item-title a"
    assert root.cssselect(selector)[0].text.strip() == "Story headline here"


def test_analyzer_rejects_bare_tag_item_selector():
    """Unclassed wrapper divs must not produce a generic ``div`` item selector."""
    html = b"""<!DOCTYPE html><html><head><title>Press</title></head><body>
    <main><div class="grid">
      <div><div class="x-card"><div class="x-card-subhead">03.07.2026</div>
        <a class="stretched-link" href="/a">First headline long enough here</a></div></div>
      <div><div class="x-card"><div class="x-card-subhead">02.07.2026</div>
        <a class="stretched-link" href="/b">Second headline long enough here</a></div></div>
      <div><div class="x-card"><div class="x-card-subhead">01.07.2026</div>
        <a class="stretched-link" href="/c">Third headline long enough here</a></div></div>
    </div></main></body></html>"""
    spec = SpecAnalyzer(filtered_text_length=150).analyze(
        "https://example.com/press", data=html
    )
    assert spec.items.selector == "./*"
    feed = SpecExtractor().extract(
        "https://example.com/press", spec, data=html
    )
    assert len(feed["items"]) == 3
    assert feed["items"][0]["link"] == "https://example.com/a"


def test_analyzer_prefers_news_list_over_form_select():
    """Callback-form time slots must not beat a real news listing cluster."""
    html = b"""<!DOCTYPE html><html><head><title>Press</title></head><body>
    <form class="callback-form">
      <select class="callback-form__select">
        <option>06.07.2026 11:00 - 13:00</option>
        <option>06.07.2026 13:00 - 15:00</option>
        <option>06.07.2026 15:00 - 17:00</option>
        <option>07.07.2026 11:00 - 13:00</option>
        <option>07.07.2026 13:00 - 15:00</option>
        <option>07.07.2026 15:00 - 17:00</option>
        <option>08.07.2026 11:00 - 13:00</option>
        <option>08.07.2026 13:00 - 15:00</option>
        <option>08.07.2026 15:00 - 17:00</option>
      </select>
    </form>
    <div class="news-block">
      <div class="one-news">
        <b>02.07.2026</b>
        <a href="/about/news/15514/">First headline long enough here</a>
        <div class="preview-text">Preview text for the first story here.</div>
      </div>
      <div class="one-news">
        <b>01.07.2026</b>
        <a href="/about/news/15507/">Second headline long enough here</a>
        <div class="preview-text">Preview text for the second story here.</div>
      </div>
      <div class="one-news">
        <b>12.06.2026</b>
        <a href="/about/news/15454/">Third headline long enough here</a>
        <div class="preview-text">Preview text for the third story here.</div>
      </div>
    </div>
    </body></html>"""
    spec = SpecAnalyzer(filtered_text_length=150).analyze(
        "https://example.com/press", data=html, require_items=True
    )
    assert spec.items.selector == "div.one-news"
    assert set(spec.fields) >= {"date", "title", "link"}
    feed = SpecExtractor().extract(
        "https://example.com/press", spec, data=html
    )
    assert len(feed["items"]) == 3
    assert feed["items"][0]["link"] == "https://example.com/about/news/15514/"


def test_selector_specific_enough():
    assert SpecAnalyzer._selector_specific_enough("div", 265, 24) is False
    assert SpecAnalyzer._selector_specific_enough("div", 24, 24) is True
    assert SpecAnalyzer._selector_specific_enough("li.news-item", 4, 4) is True
    assert SpecAnalyzer._selector_specific_enough("li.news-item", 20, 4) is False
    assert SpecAnalyzer._selector_specific_enough("div.one-news", 3, 2) is True


def _wordpress_mixed_category_html():
    articles = []
    categories = [
        "category-nzc-news",
        "category-nzc-news",
        "category-european-news",
        "category-european-news",
        "category-events",
        "category-nzc-news",
    ]
    dates = [
        "2026-07-02T14:08:09+02:00",
        "2026-06-05T10:22:17+02:00",
        "2026-05-28T16:31:19+02:00",
        "2026-05-28T12:30:14+02:00",
        "2026-05-26T11:54:53+02:00",
        "2026-05-11T13:42:52+02:00",
    ]
    titles = [
        "First headline long enough for the analyzer here",
        "Second headline long enough for the analyzer here",
        "Third headline long enough for the analyzer here",
        "Fourth headline long enough for the analyzer here",
        "Fifth headline long enough for the analyzer here",
        "Sixth headline long enough for the analyzer here",
    ]
    for idx, (category, date, title) in enumerate(
        zip(categories, dates, titles), start=1
    ):
        articles.append(
            """
      <article class="fusion-post-grid post-%d type-post status-publish hentry %s">
        <span class="updated">%s</span>
        <h2 class="blog-shortcode-post-title"><a href="/news/%d/">%s</a></h2>
      </article>"""
            % (15000 + idx, category, date, idx, title)
        )
    body = """
    <div class="fusion-posts-container">
      %s
    </div>
    """ % (
        "\n".join(articles)
    )
    return (
        b"""<!DOCTYPE html><html><head><title>Latest News</title></head><body>"""
        + body.encode("utf-8")
        + b"""</body></html>"""
    )


def test_analyzer_ignores_wordpress_taxonomy_classes_for_items():
    """Mixed category-* classes must not shrink the item selector."""
    html = _wordpress_mixed_category_html()
    spec = SpecAnalyzer(filtered_text_length=150).analyze(
        "https://example.com/latest-news/", data=html, require_items=True
    )
    assert spec.items.selector == "article.fusion-post-grid"
    feed = SpecExtractor().extract(
        "https://example.com/latest-news/", spec, data=html
    )
    assert len(feed["items"]) == 6


def _html_time_news_list_html():
    return b"""<!DOCTYPE html><html><head><title>News</title></head><body>
    <div class="grid">
      <article class="post">
        <time class="date" datetime="2025-10-28T11:20:41+00:00">October 28, 2025</time>
        <a href="/story-a">First headline long enough here today</a>
      </article>
      <article class="post">
        <time class="date" datetime="2025-09-15T09:00:00+00:00">September 15, 2025</time>
        <a href="/story-b">Second headline long enough here today</a>
      </article>
      <article class="post">
        <time class="date" datetime="2025-08-01T08:30:00+00:00">August 1, 2025</time>
        <a href="/story-c">Third headline long enough here today</a>
      </article>
    </div></body></html>"""


def test_spec_extractor_parses_html_time_pattern():
    """Legacy specs with ``html:time`` must parse ``<time datetime>`` nodes."""
    html = _html_time_news_list_html()
    spec = FeedSpec(
        source_url="https://example.com/news",
        title="News",
        language="en",
        items=ItemsRule(selector="article.post", selector_type="css"),
        fields={
            "date": FieldRule(
                selector="time.date",
                source="text",
                patterns=["html:time"],
                required=True,
            ),
            "title": FieldRule(selector="a", source="text"),
            "link": FieldRule(selector="a", source="attr:href", absolute=True),
        },
    )
    feed = SpecExtractor().extract("https://example.com/news", spec, data=html)
    assert len(feed["items"]) == 3
    assert feed["items"][0]["pubdate"].year == 2025
    assert feed["items"][0]["pubdate"].month == 10
    assert feed["items"][0]["pubdate"].day == 28
    assert feed["items"][0]["link"] == "https://example.com/story-a"


def test_analyzer_emits_datetime_source_for_html_time():
    html = _html_time_news_list_html()
    spec = SpecAnalyzer(filtered_text_length=150).analyze(
        "https://example.com/news", data=html, require_items=True
    )
    assert spec.fields["date"].source == "attr:datetime"
    assert spec.fields["date"].patterns == ["html:time"]
    feed = SpecExtractor().extract("https://example.com/news", spec, data=html)
    assert len(feed["items"]) == 3
    assert all(item["pubdate"] is not None for item in feed["items"])

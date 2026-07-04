from newsworker.spec import (
    FeedSpec,
    FieldRule,
    ItemsRule,
    SpecAnalyzer,
    SpecExtractor,
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

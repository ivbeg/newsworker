import json
from xml.etree import ElementTree as ET

import pytest

from newsworker.formats import (
    SCAN_FORMATS,
    SUPPORTED_FORMATS,
    format_feed,
    format_scan,
)


def test_to_json_roundtrips_items(sample_feed):
    text = format_feed(sample_feed, fmt="json")
    data = json.loads(text)
    assert data["title"] == "Sample Feed"
    assert len(data["items"]) == 2
    # datetimes are serialized as ISO strings
    assert data["items"][0]["pubdate"].startswith("2024-01-01")


def test_rss_is_valid_xml_with_entries(sample_feed):
    text = format_feed(sample_feed, fmt="rss", public_url="https://example.com/feed")
    root = ET.fromstring(text)
    items = root.findall("./channel/item")
    assert len(items) == 2
    titles = [i.findtext("title") for i in items]
    assert "First headline" in titles


def test_atom_is_valid_xml(sample_feed):
    text = format_feed(sample_feed, fmt="atom")
    root = ET.fromstring(text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall("a:entry", ns)
    assert len(entries) == 2


def test_csv_has_header_and_rows(sample_feed):
    text = format_feed(sample_feed, fmt="csv")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].split(",")[0] == "title"
    assert len(lines) == 3  # header + 2 items


def test_format_feed_rejects_unknown_format(sample_feed):
    with pytest.raises(ValueError):
        format_feed(sample_feed, fmt="pdf")


def test_jsonfeed_is_valid_11(sample_feed):
    data = json.loads(
        format_feed(sample_feed, fmt="jsonfeed", public_url="https://example.com/feed")
    )
    assert data["version"] == "https://jsonfeed.org/version/1.1"
    assert data["feed_url"] == "https://example.com/feed"
    assert len(data["items"]) == 2
    first = data["items"][0]
    assert first["id"] == "id-1"
    assert first["url"] == "https://example.com/news/1"
    assert first["content_text"] == "First description"
    assert first["date_published"].startswith("2024-01-01")
    # per-item image mapped from extra.images
    assert first["image"] == "https://example.com/img/1.jpg"


def test_html_preview_escapes_and_lists_items(sample_feed):
    text = format_feed(sample_feed, fmt="html")
    assert text.lstrip().startswith("<!DOCTYPE html>")
    assert text.count('<article class="card">') == 2
    assert "First headline" in text


def test_html_escapes_markup():
    feed = {
        "title": "T",
        "items": [{"title": "<script>x</script>", "unique_id": "1"}],
    }
    text = format_feed(feed, fmt="html")
    assert "<script>x</script>" not in text
    assert "&lt;script&gt;" in text


def test_markdown_lists_items(sample_feed):
    text = format_feed(sample_feed, fmt="markdown")
    lines = text.splitlines()
    assert lines[0] == "# Sample Feed"
    assert "[First headline](https://example.com/news/1)" in text
    assert text.count("\n- ") == 2


def test_yaml_roundtrips(sample_feed):
    import yaml as _yaml

    data = _yaml.safe_load(format_feed(sample_feed, fmt="yaml"))
    assert data["title"] == "Sample Feed"
    assert len(data["items"]) == 2


def test_new_formats_registered():
    for fmt in ("jsonfeed", "html", "markdown", "yaml"):
        assert fmt in SUPPORTED_FORMATS


def test_naive_datetime_assumed_utc(sample_feed):
    # feedgen requires tz-aware datetimes; naive ones must be coerced to UTC.
    text = format_feed(sample_feed, fmt="rss")
    assert "+0000" in text or "GMT" in text


def test_scan_json(sample_scan_results):
    data = json.loads(format_scan(sample_scan_results, fmt="json"))
    assert len(data["items"]) == 2


def test_scan_csv(sample_scan_results):
    text = format_scan(sample_scan_results, fmt="csv")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[0].startswith("title,url,feedtype")
    assert len(lines) == 3


def test_scan_opml_is_valid_xml(sample_scan_results):
    text = format_scan(sample_scan_results, fmt="opml")
    root = ET.fromstring(text)
    outlines = root.findall("./body/outline")
    assert len(outlines) == 2
    assert outlines[0].get("xmlUrl") == "https://example.com/feed.xml"


def test_scan_rss_valid(sample_scan_results):
    root = ET.fromstring(format_scan(sample_scan_results, fmt="rss"))
    assert len(root.findall("./channel/item")) == 2


def test_scan_rejects_unknown_format(sample_scan_results):
    with pytest.raises(ValueError):
        format_scan(sample_scan_results, fmt="pdf")


def test_format_constant_sets():
    assert "json" in SUPPORTED_FORMATS
    assert "opml" in SCAN_FORMATS

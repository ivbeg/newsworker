"""Tests for per-item author/category enrichment and formatter propagation."""

import json
from xml.etree import ElementTree as ET

from newsworker.enrich import enrich_feed, enrich_item, extract_author, extract_categories
from newsworker.formats import format_feed


AUTHOR_HTML = """
<div class="post">
  <h2>Headline</h2>
  <a rel="author" href="/u/jane">Jane Doe</a>
  <ul class="tags"><li><a rel="tag" href="/t/eu">EU</a></li>
  <li><a rel="tag" href="/t/finance">Finance</a></li></ul>
</div>
"""

META_AUTHOR_HTML = '<article><meta name="Author" content="Meta Writer"><p>Body</p></article>'


def test_extract_author_rel_author():
    assert extract_author(AUTHOR_HTML) == "Jane Doe"


def test_extract_author_meta():
    assert extract_author(META_AUTHOR_HTML) == "Meta Writer"


def test_extract_categories_rel_tag():
    assert extract_categories(AUTHOR_HTML) == ["EU", "Finance"]


def test_extract_author_none_when_absent():
    assert extract_author("<div><p>no author</p></div>") is None
    assert extract_categories("<div><p>x</p></div>") == []


def test_enrich_item_populates_fields():
    item = {"title": "x", "raw_html": AUTHOR_HTML.encode("utf-8")}
    enrich_item(item)
    assert item["author"] == "Jane Doe"
    assert item["categories"] == ["EU", "Finance"]


def test_enrich_item_preserves_existing():
    item = {"title": "x", "author": "Existing", "raw_html": AUTHOR_HTML}
    enrich_item(item)
    assert item["author"] == "Existing"


def _feed_with_enriched_item():
    feed = {
        "title": "T",
        "language": "en",
        "link": "https://example.com",
        "description": "T",
        "items": [
            {
                "title": "Headline",
                "description": "d",
                "pubdate": None,
                "unique_id": "1",
                "link": "https://example.com/1",
                "author": "Jane Doe",
                "categories": ["EU", "Finance"],
                "extra": {"links": [], "images": ["https://example.com/img.jpg"]},
            }
        ],
    }
    return feed


def test_rss_emits_categories():
    text = format_feed(_feed_with_enriched_item(), fmt="rss")
    root = ET.fromstring(text)
    item = root.find("./channel/item")
    categories = [c.text for c in item.findall("category")]
    assert "EU" in categories and "Finance" in categories


def test_atom_emits_author_name():
    text = format_feed(_feed_with_enriched_item(), fmt="atom")
    root = ET.fromstring(text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    name = root.find("./a:entry/a:author/a:name", ns)
    assert name is not None and name.text == "Jane Doe"


def test_csv_has_author_and_categories_columns():
    text = format_feed(_feed_with_enriched_item(), fmt="csv")
    header = text.splitlines()[0]
    assert "author" in header
    assert "categories" in header
    assert "Jane Doe" in text
    assert "EU, Finance" in text


def test_jsonfeed_emits_authors_and_tags():
    data = json.loads(format_feed(_feed_with_enriched_item(), fmt="jsonfeed"))
    entry = data["items"][0]
    assert entry["authors"] == [{"name": "Jane Doe"}]
    assert entry["tags"] == ["EU", "Finance"]


def test_enclosure_length_uses_known_value():
    feed = _feed_with_enriched_item()
    feed["items"][0]["extra"]["enclosure_length"] = 12345
    text = format_feed(feed, fmt="rss")
    assert 'length="12345"' in text


def test_enrich_feed_returns_feed():
    feed = {"items": [{"raw_html": AUTHOR_HTML}]}
    assert enrich_feed(feed) is feed
    assert feed["items"][0]["author"] == "Jane Doe"

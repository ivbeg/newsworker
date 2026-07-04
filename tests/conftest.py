import datetime
import os

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture_path(name):
    return os.path.join(FIXTURES_DIR, name)


def read_fixture_bytes(name):
    with open(fixture_path(name), "rb") as handle:
        return handle.read()


@pytest.fixture
def news_list_html():
    """Raw bytes of the sample news-listing page."""
    return read_fixture_bytes("news_list.html")


@pytest.fixture
def news_cards_html():
    """Raw bytes of a card-style layout with per-item images."""
    return read_fixture_bytes("news_cards.html")


@pytest.fixture
def sample_feed():
    """A minimal internal feed dict used by formatter tests."""
    return {
        "title": "Sample Feed",
        "language": "en",
        "link": "https://example.com/news",
        "description": "Sample Feed",
        "items": [
            {
                "title": "First headline",
                "description": "First description",
                "pubdate": datetime.datetime(2024, 1, 1, 12, 0, 0),
                "unique_id": "id-1",
                "link": "https://example.com/news/1",
                "extra": {
                    "links": ["https://example.com/news/1"],
                    "images": ["https://example.com/img/1.jpg"],
                },
            },
            {
                "title": "Second headline",
                "description": "Second description",
                "pubdate": datetime.datetime(2024, 1, 2, 8, 30, 0),
                "unique_id": "id-2",
                "link": "https://example.com/news/2",
                "extra": {"links": ["https://example.com/news/2"], "images": []},
            },
        ],
    }


@pytest.fixture
def sample_scan_results():
    """A scan result dict used by scan-formatter tests."""
    return {
        "url": "https://example.com",
        "items": [
            {
                "title": "Example RSS",
                "url": "https://example.com/feed.xml",
                "feedtype": "rss",
                "num_entries": 10,
                "language": "en",
                "confidence": 1,
            },
            {
                "title": "Example Atom",
                "url": "https://example.com/atom.xml",
                "feedtype": "atom",
            },
        ],
    }

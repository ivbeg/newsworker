"""Work a feed build does once: one parse of the page, one qddate session per parser."""

import datetime as dt
import hashlib

import pytest
import yaml
from lxml import etree
from lxml.html import fromstring

import newsworker.extractor as extractor_module
from newsworker.dates import thread_date_parser
from newsworker.extractor import FeedExtractor
from newsworker.relative import looks_relative, read_relative
from newsworker.runtime import ExtractionContext
from newsworker.service import FeedService
from newsworker.settings import Settings
from newsworker.spec import FeedSpec, SpecExtractor
from newsworker.spec.model import FieldRule, ItemsRule
from newsworker.spec.selectors import css_select
from newsworker.tagmapper import TagPath

NOW = dt.datetime(2022, 6, 1, 12, tzinfo=dt.timezone.utc)

_LISTING = """<html lang="ru"><head><title>Новости</title></head><body><ul class="news">
<li class="item"><a href="/a">Первая новость дня</a> <span class="date">5 мая 2022</span></li>
<li class="item"><a href="/b">Вторая новость дня</a> <span class="date">6 мая 2022</span></li>
<li class="item"><a href="/c">Третья новость дня</a> <span class="date">7 мая 2022</span></li>
</ul></body></html>"""


def _service(tmp_path):
    return FeedService(
        settings=Settings(cache_dir=str(tmp_path), respect_robots=False),
        use_cache=False,
        plugins=[],
        bridges=[],
        clock=lambda: NOW,
    )


def test_a_build_parses_the_page_once(tmp_path, monkeypatch):
    parsed = []
    original = extractor_module.fromstring

    def counting(*args, **kwargs):
        parsed.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(extractor_module, "fromstring", counting)
    feed = _service(tmp_path).get_feed("https://example.ru/", data=_LISTING.encode())
    assert [item["title"] for item in feed["items"]] == [
        "Первая новость дня",
        "Вторая новость дня",
        "Третья новость дня",
    ]
    # Spec analysis, spec extraction and the structured-data step share one tree.
    assert len(parsed) == 1


def test_parse_page_outside_a_build_keeps_no_tree():
    extractor = FeedExtractor()
    data = _LISTING.encode()
    assert extractor.parse_page(data) is not extractor.parse_page(data)
    context = ExtractionContext()
    with extractor.activate_context(context):
        document = extractor.parse_page(data)
        assert extractor.parse_page(data) is document
        # Other bytes (here equal, but another object) are parsed again.
        copy = data[:-1] + data[-1:]
        assert copy is not data
        assert extractor.parse_page(copy) is not document
    context.close()
    assert context.page_document is None


def test_microdata_keeps_the_spaces_between_elements(tmp_path):
    articles = "".join(
        f"""<article itemscope itemtype="https://schema.org/NewsArticle">
<h2 itemprop="headline"><mark>Story</mark> <mark>{name}</mark></h2>
<a itemprop="url" href="/{name.lower()}">Read</a>
<meta itemprop="datePublished" content="2022-05-0{day}T10:00:00Z"></article>"""
        for day, name in ((5, "One"), (6, "Two"))
    )
    page = f"<html><head><title>News</title></head><body>{articles}</body></html>"
    feed = _service(tmp_path).get_feed("https://example.com/", data=page.encode())
    # Without whitespace-only text the headline would read "StoryOne".
    assert [item["title"] for item in feed["items"]] == ["Story One", "Story Two"]


def test_spec_items_share_one_session_per_parser(monkeypatch):
    key = thread_date_parser().match("5 мая 2022")["pattern"]["key"]
    started = []
    parsers = (thread_date_parser("ru"), thread_date_parser())
    for parser in parsers:
        original = parser.start_session

        def start(keys, _original=original):
            started.append(tuple(keys))
            return _original(keys)

        monkeypatch.setattr(parser, "start_session", start)
    spec = FeedSpec(
        source_url="https://example.ru/",
        items=ItemsRule(selector="li"),
        fields={
            "title": FieldRule(selector="a"),
            "date": FieldRule(selector="span", patterns=[key]),
        },
    )
    feed = SpecExtractor(FeedExtractor()).extract(
        "https://example.ru/", spec, data=_LISTING.encode(), context=ExtractionContext()
    )
    assert [item["pubdate"].day for item in feed["items"]] == [5, 6, 7]
    # Once per parser for the three dates, not once per date.
    assert started == [(key,), (key,)]
    assert [parser.cachedpats for parser in parsers] == [None, None]


def test_css_select_matches_cssselect_for_both_element_kinds():
    markup = (
        "<html><body><div class='a b'><p>1</p><P>2</P><span class='a'>3</span>"
        "<!-- note --></div></body></html>"
    )
    for document in (fromstring(markup), fromstring(markup, parser=etree.HTMLParser())):
        for selector in ("div.a p", "span.a", "DIV P", "p:first-child", "div > *"):
            assert css_select(document, selector) == document.cssselect(selector)


def test_relative_dates_need_a_keyword_after_spaces_are_collapsed():
    assert read_relative("il  y a\n3 heures", now=NOW) is not None
    assert read_relative("Только\tчто", now=NOW) is not None
    assert read_relative("8 comments", now=NOW) is None
    assert looks_relative("Posted YESTERDAY")
    assert not looks_relative("Page 2")


def test_tag_path_hash_is_the_md5_of_its_key():
    document = fromstring("<html><body><div><p><b>x</b></p></div></body></html>")
    path = TagPath(document.xpath("//b")[0])
    assert path.level == 5
    assert path.hash == hashlib.md5(path.key.encode("utf8"), usedforsecurity=False).hexdigest()


def test_spec_yaml_is_read_with_a_safe_loader():
    spec = FeedSpec(
        source_url="https://example.ru/",
        items=ItemsRule(selector="li"),
        fields={"date": FieldRule(selector="span", patterns=["dt:date:date_rus"])},
    )
    assert FeedSpec.from_yaml(spec.to_yaml()).to_dict() == spec.to_dict()
    with pytest.raises(yaml.YAMLError):
        FeedSpec.from_yaml("items: !!python/object/apply:os.getcwd []\n")

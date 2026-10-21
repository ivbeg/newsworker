"""Dates are matched with the page language's qddate parser first (N1)."""

import threading

import pytest
from lxml.html import fromstring

from newsworker.dates import qddate_language, thread_date_parser
from newsworker.extractor import FeedExtractor
from newsworker.runtime import ExtractionContext
from newsworker.spec import FeedSpec, SpecExtractor
from newsworker.spec.model import FieldRule, ItemsRule


def _languages(parser):
    return {pattern.get("language") for pattern in parser.patterns}


@pytest.mark.parametrize(
    ("tag", "code"),
    [("ru", "ru"), ("cs", "cz"), ("cs-CZ", "cz"), ("en-US", "en"), ("pt_BR", "pt")],
)
def test_qddate_language_maps_page_tags(tag, code):
    assert qddate_language(tag) == code


@pytest.mark.parametrize("tag", [None, "", "ja", "zh-CN"])
def test_qddate_language_is_none_without_patterns(tag):
    assert qddate_language(tag) is None


def test_language_parser_knows_one_language_and_numeric_dates():
    parser = thread_date_parser("ru")
    assert _languages(parser) <= {None, "ru", "en"}
    english = {p["basekey"] for p in parser.patterns if p.get("language") == "en"}
    # Only the US month-first numeric dates are filed under English.
    assert english == {"dt:date:date_usa", "dt:date:date_usa_1"}
    assert len(parser.patterns) < len(thread_date_parser().patterns) / 4
    assert thread_date_parser("ru") is parser
    seen = []
    worker = threading.Thread(target=lambda: seen.append(thread_date_parser("ru")))
    worker.start()
    worker.join()
    assert seen[0] is not parser


def test_language_parser_rejects_unknown_codes():
    with pytest.raises(ValueError):
        thread_date_parser("cs")  # qddate spells Czech "cz"


@pytest.mark.parametrize(
    "text", ["05.06.2022", "05/13/2022", "13/05/2022", "2022-05-06", "05.06.2022 10:30", "05/06/22"]
)
def test_numeric_dates_read_the_same_with_any_parser(text):
    general = thread_date_parser().match(text)
    for language in ("ru", "de", "cz"):
        got = thread_date_parser(language).match(text)
        assert got["pattern"]["key"] == general["pattern"]["key"]
        assert dict(got["values"]) == dict(general["values"])


class _Spy:
    def __init__(self, monkeypatch, parser):
        self.calls = []
        original = parser.match

        def match(text, *args, **kwargs):
            self.calls.append(text)
            return original(text, *args, **kwargs)

        monkeypatch.setattr(parser, "match", match)


def _extractor_for(html):
    extractor = FeedExtractor()
    context = ExtractionContext()
    return extractor, context, fromstring(html)


def test_page_language_parser_is_tried_first(monkeypatch):
    extractor, context, document = _extractor_for("<html lang='ru-RU'><body></body></html>")
    page = _Spy(monkeypatch, thread_date_parser("ru"))
    general = _Spy(monkeypatch, thread_date_parser())
    with extractor.activate_context(context):
        extractor.initfeed(document, "https://example.ru/")
        assert context.date_language == "ru"
        matched, key, _pattern, _text, value = extractor.match_text("5 мая 2022")
    assert matched and key.startswith("dt:date:date_rus")
    assert value.date().isoformat() == "2022-05-05"
    assert page.calls == ["5 мая 2022"]
    assert general.calls == []


def test_wrong_page_language_falls_back_to_the_general_parser():
    extractor, context, document = _extractor_for("<html lang='de'><body></body></html>")
    with extractor.activate_context(context):
        extractor.initfeed(document, "https://example.org/")
        matched, key, _pattern, _text, value = extractor.match_text("29 July 2022")
        dateline = extractor.match_text("GENEVA, 29 July 2022")
    assert matched and value.date().isoformat() == "2022-07-29"
    assert "eng" in key
    assert dateline[0] and dateline[4] == value


def test_text_without_letters_never_reaches_the_general_parser(monkeypatch):
    extractor, context, document = _extractor_for("<html lang='ru'><body></body></html>")
    general = _Spy(monkeypatch, thread_date_parser())
    with extractor.activate_context(context):
        extractor.initfeed(document, "https://example.ru/")
        assert extractor.match_text("05.06.2022")[0]
        assert not extractor.match_text("1 234 567")[0]
    assert general.calls == []


def test_without_language_evidence_only_the_general_parser_is_used():
    extractor, context, document = _extractor_for("<html><body></body></html>")
    with extractor.activate_context(context):
        extractor.initfeed(document, "https://example.org/")
        assert context.date_language is None
        assert [language for language, _ in context.date_parsers()] == [None]


def test_explicit_default_language_and_content_language_header():
    extractor = FeedExtractor(default_language="fr")
    context = ExtractionContext()
    with extractor.activate_context(context):
        extractor.use_page_language(fromstring("<html lang='en'><body></body></html>"))
        assert context.date_language == "fr"
    header = ExtractionContext(content_language="uk")
    extractor = FeedExtractor()
    with extractor.activate_context(header):
        extractor.use_page_language(fromstring("<html><body></body></html>"))
        assert header.date_language == "uk"


def _sessions():
    return [parser.cachedpats for parser in (thread_date_parser("ru"), thread_date_parser())]


def test_sessions_narrow_every_parser_and_are_closed():
    context = ExtractionContext()
    context.set_date_language("ru")
    with context.narrowed_dates(["dt:date:date_1"]):
        # Parsers borrowed inside the block are narrowed too.
        parsers = [parser for _language, parser in context.date_parsers()]
        assert all(parser.cachedpats is not None for parser in parsers)
        with context.narrowed_dates(None):
            assert all(parser.cachedpats is None for parser in parsers)
        # Sessions start again only when a parser is asked for.
        assert all(parser.cachedpats is None for parser in parsers)
        context.date_parsers()
        assert all(parser.cachedpats is not None for parser in parsers)
    assert _sessions() == [None, None]


def test_changing_language_closes_the_old_parser_session():
    context = ExtractionContext()
    context.set_date_language("ru")
    with context.narrowed_dates(["dt:date:date_1"]):
        context.date_parsers()
        context.set_date_language("de")
        assert thread_date_parser("ru").cachedpats is None
        assert thread_date_parser("de") in [p for _language, p in context.date_parsers()]
        assert thread_date_parser("de").cachedpats is not None
    assert thread_date_parser("de").cachedpats is None
    assert thread_date_parser().cachedpats is None


_PAGE = """<html lang="ru"><body><ul>
<li><a href="/a">Первая новость дня</a> <span>5 мая 2022</span></li>
<li><a href="/b">Вторая новость дня</a> <span>6 мая 2022</span></li>
<li><a href="/c">Третья новость дня</a> <span>7 мая 2022</span></li>
</ul></body></html>"""


def _rus_key():
    return thread_date_parser().match("5 мая 2022")["pattern"]["key"]


def test_cached_patterns_apply_to_the_page_language_parser():
    extractor = FeedExtractor()
    context = ExtractionContext()
    seen = []
    original = extractor.process_clusters

    def process(*args):
        seen.extend((lang, p.cachedpats is not None) for lang, p in context.date_parsers())
        return original(*args)

    extractor.process_clusters = process
    feed, _session = extractor.get_feed(
        "https://example.ru/", data=_PAGE.encode(), cached_p=[_rus_key()], context=context
    )
    assert seen == [("ru", True), (None, True)]
    assert _sessions() == [None, None]
    assert len(feed["items"]) == 3


def test_spec_extraction_uses_the_page_language():
    spec = FeedSpec(
        source_url="https://example.ru/",
        items=ItemsRule(selector="li"),
        fields={
            "title": FieldRule(selector="a"),
            "link": FieldRule(selector="a", source="attr:href", absolute=True),
            "date": FieldRule(selector="span", patterns=[_rus_key()]),
        },
    )
    extractor = FeedExtractor()
    context = ExtractionContext()
    feed = SpecExtractor(extractor).extract(
        "https://example.ru/", spec, data=_PAGE.encode(), context=context
    )
    assert context.date_language == "ru"
    assert [item["pubdate"].day for item in feed["items"]] == [5, 6, 7]
    assert _sessions() == [None, None]


def test_repeated_text_is_matched_once_per_build(monkeypatch):
    extractor, context, document = _extractor_for("<html lang='ru'><body></body></html>")
    page = _Spy(monkeypatch, thread_date_parser("ru"))
    key = _rus_key()
    with extractor.activate_context(context):
        extractor.use_page_language(document)
        first = extractor.match_text("5 мая 2022")
        assert extractor.match_text("5 мая 2022") == first
        # A restriction that allows the matched pattern reuses the result.
        with extractor.narrowed_dates([key]):
            assert extractor.match_text("5 мая 2022") == first
        assert not extractor.match_text("Страница 2")[0]
        with extractor.narrowed_dates([key]):
            assert not extractor.match_text("Страница 2")[0]
    assert page.calls == ["5 мая 2022", "Страница 2"]
    context.close()
    with extractor.activate_context(context):
        extractor.match_text("5 мая 2022")
    assert page.calls[-1] == "5 мая 2022" and len(page.calls) == 3

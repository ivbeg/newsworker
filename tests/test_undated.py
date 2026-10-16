"""The opt-in undated listing fallback."""

import json
from pathlib import Path

from newsworker.undated import extract_undated_listing


def test_undated_listing_and_false_positive_guards():
    cards = "".join(
        f"<article class='news-card'><h2><a href='/story/{index}'>Important headline number {index}</a></h2><p>Useful summary for story {index}</p></article>"
        for index in range(4)
    )
    feed, details = extract_undated_listing(
        f"<html><head><title>News</title></head><body><main>{cards}</main></body></html>".encode(),
        "https://example.com/news",
    )
    assert len(feed["items"]) == 4
    assert all(item["pubdate"] is None for item in feed["items"])
    assert (
        feed["items"][0]["unique_id"]
        == extract_undated_listing(
            f"<html><body><main>{cards}</main></body></html>".encode(),
            "https://example.com/news",
        )[0]["items"][0]["unique_id"]
    )
    assert details["confidence"] >= 0.75

    navigation = "".join(
        f"<h2><a href='/{index}'>Navigation option {index}</a></h2>" for index in range(5)
    )
    rejected, _ = extract_undated_listing(
        f"<html><body><nav>{navigation}</nav></body></html>".encode(),
        "https://example.com",
    )
    assert rejected["items"] == []


def test_undated_labeled_corpus_precision_and_recall():
    corpus_path = Path(__file__).parent / "fixtures" / "undated" / "corpus.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    outcomes = []
    for case in corpus:
        feed, _ = extract_undated_listing(
            case["html"].encode("utf-8"),
            f"https://example.com/{case['name'].replace(' ', '-')}",
        )
        outcomes.append((case["label"], bool(feed["items"])))
    true_positive = sum(expected and actual for expected, actual in outcomes)
    false_positive = sum(not expected and actual for expected, actual in outcomes)
    false_negative = sum(expected and not actual for expected, actual in outcomes)
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    assert precision >= 0.9
    assert recall >= 0.9

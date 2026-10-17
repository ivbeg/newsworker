"""Upgrading from 1.3 must not deliver every watched item again.

1.3 identified an item by a hash of its text and stored it in the ``seen``
table; 1.4 derives ``unique_id`` from the link and keeps the text hash as
``content_hash``.
"""

import sqlite3

from newsworker.dedup import DedupStore

FEED = "https://example.com/news"


def _item(link, old_id):
    return {"title": "t", "link": link, "unique_id": "link-id-" + link[-1], "content_hash": old_id}


def test_items_seen_by_1_3_are_not_queued_again(tmp_path):
    path = str(tmp_path / "dedup.sqlite")
    legacy = sqlite3.connect(path)
    legacy.execute(
        "CREATE TABLE seen (feed TEXT NOT NULL, uid TEXT NOT NULL, ts REAL NOT NULL, PRIMARY KEY (feed, uid))"
    )
    legacy.execute("INSERT INTO seen VALUES (?, ?, ?)", (FEED, "old-1", 100.0))
    legacy.commit()
    legacy.close()

    store = DedupStore(path)
    inserted = store.enqueue(
        FEED,
        [_item("https://example.com/1", "old-1"), _item("https://example.com/2", "old-2")],
        channel="webhook",
        destination="hook",
    )
    assert [record.uid for record in inserted] == ["link-id-2"]


def test_outbox_rows_under_the_old_id_count_as_known(tmp_path):
    store = DedupStore(str(tmp_path / "dedup.sqlite"))
    first = store.enqueue(
        FEED, [{"title": "t", "unique_id": "old-1"}], channel="webhook", destination="hook"
    )
    assert len(first) == 1
    again = store.enqueue(
        FEED, [_item("https://example.com/1", "old-1")], channel="webhook", destination="hook"
    )
    assert again == []
    elsewhere = store.enqueue(
        FEED, [_item("https://example.com/1", "old-1")], channel="slack", destination="room"
    )
    assert len(elsewhere) == 1

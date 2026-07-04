#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cross-run deduplication of feed items backed by SQLite.

Records the ``unique_id`` of every item that has been seen so subsequent runs
(e.g. ``watch`` mode) can emit and deliver only genuinely new items.
"""

import os
import sqlite3
import threading
import time


class DedupStore:
    """A small SQLite-backed set of seen item ids, scoped per feed URL."""

    def __init__(self, path):
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            "feed TEXT NOT NULL, uid TEXT NOT NULL, ts REAL NOT NULL, "
            "PRIMARY KEY (feed, uid))"
        )
        self._conn.commit()

    @staticmethod
    def _uid(item):
        return (
            item.get("unique_id")
            or item.get("link")
            or item.get("title")
            or ""
        )

    def filter_new(self, feed_url, items):
        """Returns the subset of ``items`` not seen before and records them.

        Items with an empty identifier are always treated as new and are not
        recorded (they would otherwise collide).
        """
        new_items = []
        to_record = []
        now = time.time()
        with self._lock:
            for item in items:
                uid = self._uid(item)
                if not uid:
                    new_items.append(item)
                    continue
                row = self._conn.execute(
                    "SELECT 1 FROM seen WHERE feed = ? AND uid = ?",
                    (feed_url, uid),
                ).fetchone()
                if row is None:
                    new_items.append(item)
                    to_record.append((feed_url, uid, now))
            if to_record:
                self._conn.executemany(
                    "INSERT OR IGNORE INTO seen (feed, uid, ts) VALUES (?, ?, ?)",
                    to_record,
                )
                self._conn.commit()
        return new_items

    def close(self):
        with self._lock:
            self._conn.close()

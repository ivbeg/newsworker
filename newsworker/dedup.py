#!/usr/bin/env python
"""SQLite delivery outbox with restart-safe, destination-scoped acknowledgment."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class OutboxRecord:
    idempotency_key: str
    feed: str
    uid: str
    channel: str
    destination: str
    payload: Dict[str, Any]
    status: str
    attempts: int
    next_attempt: float
    last_error: Optional[str]


class DedupStore:
    """Durable outbox retaining the legacy seen-set compatibility API."""

    def __init__(self, path: str, *, clock=time.time):
        self.path = path
        self.clock = clock
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            "feed TEXT NOT NULL, uid TEXT NOT NULL, ts REAL NOT NULL, "
            "PRIMARY KEY (feed, uid))"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS outbox ("
            "idempotency_key TEXT PRIMARY KEY, feed TEXT NOT NULL, uid TEXT NOT NULL, "
            "channel TEXT NOT NULL, destination TEXT NOT NULL, payload TEXT NOT NULL, "
            "status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
            "next_attempt REAL NOT NULL, last_error TEXT, created_at REAL NOT NULL, "
            "updated_at REAL NOT NULL, delivered_at REAL, "
            "UNIQUE(feed, uid, channel, destination))"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS outbox_due ON outbox(status, next_attempt)")
        self._migrate_seen()
        self._conn.commit()

    @staticmethod
    def _uid(item: Dict[str, Any]) -> str:
        return str(item.get("unique_id") or item.get("link") or item.get("title") or "")

    @staticmethod
    def idempotency_key(feed: str, uid: str, channel: str, destination: str) -> str:
        value = "\x1f".join((feed, uid, channel, destination))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _migrate_seen(self) -> None:
        now = self.clock()
        rows = self._conn.execute("SELECT feed, uid, ts FROM seen").fetchall()
        for row in rows:
            key = self.idempotency_key(row["feed"], row["uid"], "legacy", "seen")
            self._conn.execute(
                "INSERT OR IGNORE INTO outbox "
                "(idempotency_key, feed, uid, channel, destination, payload, status, "
                "attempts, next_attempt, created_at, updated_at, delivered_at) "
                "VALUES (?, ?, ?, 'legacy', 'seen', '{}', 'delivered', 1, ?, ?, ?, ?)",
                (key, row["feed"], row["uid"], now, row["ts"], now, row["ts"]),
            )

    def enqueue(
        self,
        feed: str,
        items: Iterable[Dict[str, Any]],
        *,
        channel: str,
        destination: str,
    ) -> List[OutboxRecord]:
        now = self.clock()
        inserted = []
        with self._lock, self._conn:
            for item in items:
                uid = self._uid(item)
                if not uid:
                    continue
                key = self.idempotency_key(feed, uid, channel, destination)
                legacy_seen = self._conn.execute(
                    "SELECT ts FROM seen WHERE feed=? AND uid=?", (feed, uid)
                ).fetchone()
                status = "delivered" if legacy_seen else "pending"
                attempts = 1 if legacy_seen else 0
                delivered_at = legacy_seen["ts"] if legacy_seen else None
                cursor = self._conn.execute(
                    "INSERT OR IGNORE INTO outbox "
                    "(idempotency_key, feed, uid, channel, destination, payload, status, "
                    "attempts, next_attempt, created_at, updated_at, delivered_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        feed,
                        uid,
                        channel,
                        destination,
                        json.dumps(item, ensure_ascii=False, default=_json_default),
                        status,
                        attempts,
                        now,
                        now,
                        now,
                        delivered_at,
                    ),
                )
                if cursor.rowcount and not legacy_seen:
                    inserted.append(self.get(key))
        return [record for record in inserted if record is not None]

    def get(self, key: str) -> Optional[OutboxRecord]:
        row = self._conn.execute(
            "SELECT * FROM outbox WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _record(row) if row else None

    def claim_due(
        self,
        *,
        feed: Optional[str] = None,
        channel: Optional[str] = None,
        destination: Optional[str] = None,
        limit: int = 100,
        lease_seconds: float = 60,
    ) -> List[OutboxRecord]:
        now = self.clock()
        where = ["status IN ('pending', 'retry')", "next_attempt <= ?"]
        params: List[Any] = [now]
        if feed is not None:
            where.append("feed = ?")
            params.append(feed)
        if channel is not None:
            where.append("channel = ?")
            params.append(channel)
        if destination is not None:
            where.append("destination = ?")
            params.append(destination)
        params.append(max(1, limit))
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT * FROM outbox WHERE "
                + " AND ".join(where)
                + " ORDER BY created_at, idempotency_key LIMIT ?",
                params,
            ).fetchall()
            claimed = []
            for row in rows:
                updated = self._conn.execute(
                    "UPDATE outbox SET status='claimed', attempts=attempts+1, "
                    "next_attempt=?, updated_at=? WHERE idempotency_key=? "
                    "AND status IN ('pending','retry')",
                    (now + lease_seconds, now, row["idempotency_key"]),
                )
                if updated.rowcount:
                    claimed_row = dict(row)
                    claimed_row.update(
                        {
                            "status": "claimed",
                            "attempts": row["attempts"] + 1,
                            "next_attempt": now + lease_seconds,
                        }
                    )
                    claimed.append(_record(claimed_row))
            return claimed

    def acknowledge(self, key: str) -> None:
        now = self.clock()
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE outbox SET status='delivered', delivered_at=?, updated_at=?, "
                "last_error=NULL WHERE idempotency_key=?",
                (now, now, key),
            )

    def fail(
        self,
        key: str,
        error: str,
        *,
        backoff: float = 1.0,
        terminal: bool = False,
    ) -> None:
        now = self.clock()
        record = self.get(key)
        attempts = record.attempts if record else 1
        next_attempt = now + max(0.0, backoff) * (2 ** max(0, attempts - 1))
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE outbox SET status=?, next_attempt=?, last_error=?, updated_at=? "
                "WHERE idempotency_key=?",
                (
                    "terminal" if terminal else "retry",
                    next_attempt,
                    str(error)[:1000],
                    now,
                    key,
                ),
            )

    def release_expired_claims(self) -> int:
        now = self.clock()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE outbox SET status='retry', updated_at=? "
                "WHERE status='claimed' AND next_attempt <= ?",
                (now, now),
            )
            return cursor.rowcount

    def prune(self, retention_days: int = 30) -> int:
        cutoff = self.clock() - retention_days * 86400
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM outbox WHERE status='delivered' AND delivered_at < ?",
                (cutoff,),
            )
            self._conn.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
            return cursor.rowcount

    def counts(
        self,
        *,
        feed: Optional[str] = None,
        channel: Optional[str] = None,
        destination: Optional[str] = None,
    ) -> Dict[str, int]:
        where = []
        params: List[Any] = []
        for column, value in (
            ("feed", feed),
            ("channel", channel),
            ("destination", destination),
        ):
            if value is not None:
                where.append(f"{column} = ?")
                params.append(value)
        sql = "SELECT status, count(*) AS count FROM outbox"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY status"
        rows = self._conn.execute(sql, params).fetchall()
        return {row["status"]: row["count"] for row in rows}

    def filter_new(self, feed_url: str, items: Iterable[Dict[str, Any]]):
        """Compatibility seen-set API; new watch code uses the outbox methods."""
        new_items = []
        now = self.clock()
        with self._lock, self._conn:
            for item in items:
                uid = self._uid(item)
                if not uid:
                    new_items.append(item)
                    continue
                row = self._conn.execute(
                    "SELECT 1 FROM seen WHERE feed=? AND uid=?", (feed_url, uid)
                ).fetchone()
                if row is None:
                    new_items.append(item)
                    self._conn.execute(
                        "INSERT INTO seen(feed, uid, ts) VALUES (?, ?, ?)",
                        (feed_url, uid, now),
                    )
        return new_items

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _record(row) -> OutboxRecord:
    return OutboxRecord(
        idempotency_key=row["idempotency_key"],
        feed=row["feed"],
        uid=row["uid"],
        channel=row["channel"],
        destination=row["destination"],
        payload=json.loads(row["payload"] or "{}"),
        status=row["status"],
        attempts=row["attempts"],
        next_attempt=row["next_attempt"],
        last_error=row["last_error"],
    )


def _json_default(value):
    isoformat = getattr(value, "isoformat", None)
    if isoformat:
        return isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    raise TypeError(type(value).__name__)

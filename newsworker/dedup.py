#!/usr/bin/env python
"""SQLite delivery outbox with restart-safe, destination-scoped acknowledgment."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
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
    claim_token: Optional[str] = None
    feed_meta: Optional[Dict[str, Any]] = None


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
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS items ("
            "feed TEXT NOT NULL, uid TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, "
            "content_hash TEXT NOT NULL, title TEXT, link TEXT, pubdate TEXT, "
            "first_seen REAL NOT NULL, last_seen REAL NOT NULL, updated_at REAL, "
            "PRIMARY KEY (feed, uid))"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS items_seen ON items(feed, first_seen)")
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(outbox)")}
        if "claim_token" not in columns:
            self._conn.execute("ALTER TABLE outbox ADD COLUMN claim_token TEXT")
        if "feed_meta" not in columns:
            self._conn.execute("ALTER TABLE outbox ADD COLUMN feed_meta TEXT")
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
        feed_meta: Optional[Dict[str, Any]] = None,
    ) -> List[OutboxRecord]:
        """Queue items not seen before; ``feed_meta`` lets retries run without a new poll."""
        now = self.clock()
        inserted = []
        meta_json = json.dumps(feed_meta or {}, ensure_ascii=False, default=_json_default)
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
                    "attempts, next_attempt, created_at, updated_at, delivered_at, feed_meta) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        meta_json,
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
                token = uuid.uuid4().hex
                updated = self._conn.execute(
                    "UPDATE outbox SET status='claimed', attempts=attempts+1, "
                    "next_attempt=?, updated_at=?, claim_token=? WHERE idempotency_key=? "
                    "AND status IN ('pending','retry')",
                    (now + lease_seconds, now, token, row["idempotency_key"]),
                )
                if updated.rowcount:
                    claimed_row = dict(row)
                    claimed_row.update(
                        {
                            "status": "claimed",
                            "attempts": row["attempts"] + 1,
                            "next_attempt": now + lease_seconds,
                            "claim_token": token,
                        }
                    )
                    claimed.append(_record(claimed_row))
            return claimed

    def renew(self, key: str, token: str, lease_seconds: float = 60) -> bool:
        """Extend an active claim; returns False when the claim was lost."""
        now = self.clock()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE outbox SET next_attempt=?, updated_at=? "
                "WHERE idempotency_key=? AND status='claimed' AND claim_token=?",
                (now + lease_seconds, now, key, token),
            )
            return bool(cursor.rowcount)

    def acknowledge(self, key: str, token: Optional[str] = None) -> bool:
        """Mark delivered. With ``token``, only the current claim holder may do so."""
        now = self.clock()
        sql = (
            "UPDATE outbox SET status='delivered', delivered_at=?, updated_at=?, "
            "last_error=NULL, claim_token=NULL WHERE idempotency_key=?"
        )
        params: List[Any] = [now, now, key]
        if token is not None:
            sql += " AND claim_token=? AND status='claimed'"
            params.append(token)
        with self._lock, self._conn:
            return bool(self._conn.execute(sql, params).rowcount)

    def fail(
        self,
        key: str,
        error: str,
        *,
        backoff: float = 1.0,
        terminal: bool = False,
        token: Optional[str] = None,
    ) -> bool:
        """Record a failed attempt.

        With ``token``, a worker whose lease expired (and whose record another
        worker may already have delivered) cannot overwrite the newer state.
        """
        now = self.clock()
        record = self.get(key)
        attempts = record.attempts if record else 1
        next_attempt = now + max(0.0, backoff) * (2 ** max(0, attempts - 1))
        sql = (
            "UPDATE outbox SET status=?, next_attempt=?, last_error=?, updated_at=?, "
            "claim_token=NULL WHERE idempotency_key=?"
        )
        params: List[Any] = [
            "terminal" if terminal else "retry",
            next_attempt,
            str(error)[:1000],
            now,
            key,
        ]
        if token is not None:
            sql += " AND claim_token=? AND status='claimed'"
            params.append(token)
        with self._lock, self._conn:
            return bool(self._conn.execute(sql, params).rowcount)

    def release_expired_claims(self) -> int:
        now = self.clock()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE outbox SET status='retry', updated_at=?, claim_token=NULL "
                "WHERE status='claimed' AND next_attempt <= ?",
                (now, now),
            )
            return cursor.rowcount

    def prune(self, retention_days: int = 30, history_days: int = 0) -> int:
        """Drop delivered outbox rows older than ``retention_days`` and, when
        ``history_days`` is positive, history entries not seen for that long."""
        cutoff = self.clock() - retention_days * 86400
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM outbox WHERE status='delivered' AND delivered_at < ?",
                (cutoff,),
            )
            self._conn.execute("DELETE FROM seen WHERE ts < ?", (cutoff,))
            if history_days > 0:
                self._conn.execute(
                    "DELETE FROM items WHERE last_seen < ?",
                    (self.clock() - history_days * 86400,),
                )
            return cursor.rowcount

    # -- item history -----------------------------------------------------

    @staticmethod
    def content_hash(item: Dict[str, Any]) -> str:
        """What a reader sees of an item; a change makes a new version."""
        visible = {
            key: item.get(key) for key in ("title", "description", "link", "pubdate", "content")
        }
        payload = json.dumps(visible, sort_keys=True, ensure_ascii=False, default=_json_default)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record_items(self, feed: str, items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remember every item seen on ``feed``; return the ones that changed.

        Each returned item is a copy with ``version`` (2, 3, ...) and
        ``updated: True``. Items seen for the first time are recorded as
        version 1 and not returned: they are new, not updated.
        """
        now = self.clock()
        changed = []
        with self._lock, self._conn:
            for item in items:
                uid = self._uid(item)
                if not uid:
                    continue
                digest = self.content_hash(item)
                pubdate = item.get("pubdate")
                fields = (
                    item.get("title"),
                    item.get("link"),
                    pubdate.isoformat() if hasattr(pubdate, "isoformat") else pubdate,
                )
                row = self._conn.execute(
                    "SELECT version, content_hash FROM items WHERE feed=? AND uid=?", (feed, uid)
                ).fetchone()
                if row is None:
                    self._conn.execute(
                        "INSERT INTO items (feed, uid, version, content_hash, title, link, "
                        "pubdate, first_seen, last_seen) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)",
                        (feed, uid, digest, *fields, now, now),
                    )
                elif row["content_hash"] == digest:
                    self._conn.execute(
                        "UPDATE items SET last_seen=? WHERE feed=? AND uid=?", (now, feed, uid)
                    )
                else:
                    version = row["version"] + 1
                    self._conn.execute(
                        "UPDATE items SET version=?, content_hash=?, title=?, link=?, pubdate=?, "
                        "last_seen=?, updated_at=? WHERE feed=? AND uid=?",
                        (version, digest, *fields, now, now, feed, uid),
                    )
                    changed.append({**item, "version": version, "updated": True})
        return changed

    def history(
        self, feed: Optional[str] = None, *, since: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Recorded items, newest first; ``since`` filters on ``first_seen``."""
        where, params = [], []
        if feed is not None:
            where.append("feed = ?")
            params.append(feed)
        if since is not None:
            where.append("first_seen >= ?")
            params.append(since)
        sql = "SELECT * FROM items"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY first_seen DESC, uid"
        return [dict(row) for row in self._conn.execute(sql, params).fetchall()]

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
        claim_token=_column(row, "claim_token"),
        feed_meta=json.loads(_column(row, "feed_meta") or "{}"),
    )


def _column(row, name):
    try:
        return row[name]
    except (IndexError, KeyError):
        return None


def _json_default(value):
    isoformat = getattr(value, "isoformat", None)
    if isoformat:
        return isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    raise TypeError(type(value).__name__)

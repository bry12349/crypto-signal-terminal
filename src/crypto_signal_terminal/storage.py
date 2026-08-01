from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path


class AuditStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_message_versions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              account_id TEXT NOT NULL,
              channel_id INTEGER NOT NULL,
              message_id INTEGER NOT NULL,
              version_hash TEXT NOT NULL,
              raw_text TEXT,
              observed_at TEXT NOT NULL,
              deleted INTEGER NOT NULL DEFAULT 0,
              UNIQUE(account_id, channel_id, message_id, version_hash)
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_deliveries (
              idempotency_key TEXT PRIMARY KEY,
              delivered_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def record_message_version(
        self,
        account_id: str,
        channel_id: int,
        message_id: int,
        raw_text: str,
        observed_at: datetime,
    ) -> bool:
        version_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        cursor = self._connection.execute(
            """INSERT OR IGNORE INTO telegram_message_versions
               (account_id, channel_id, message_id, version_hash, raw_text, observed_at, deleted)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (account_id, channel_id, message_id, version_hash, raw_text, observed_at.isoformat()),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def mark_message_deleted(self, account_id: str, channel_id: int, message_id: int, observed_at: datetime) -> bool:
        marker = f"deleted:{observed_at.isoformat()}"
        version_hash = hashlib.sha256(marker.encode("utf-8")).hexdigest()
        cursor = self._connection.execute(
            """INSERT OR IGNORE INTO telegram_message_versions
               (account_id, channel_id, message_id, version_hash, raw_text, observed_at, deleted)
               VALUES (?, ?, ?, ?, NULL, ?, 1)""",
            (account_id, channel_id, message_id, version_hash, observed_at.isoformat()),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def message_versions(self, account_id: str, channel_id: int, message_id: int) -> list[dict]:
        rows = self._connection.execute(
            """SELECT raw_text, observed_at, deleted, version_hash
               FROM telegram_message_versions
               WHERE account_id=? AND channel_id=? AND message_id=? ORDER BY id""",
            (account_id, channel_id, message_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def reserve_notification(self, key: str, delivered_at: datetime) -> bool:
        cursor = self._connection.execute(
            "INSERT OR IGNORE INTO notification_deliveries (idempotency_key, delivered_at) VALUES (?, ?)",
            (key, delivered_at.isoformat()),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def release_notification(self, key: str) -> None:
        self._connection.execute("DELETE FROM notification_deliveries WHERE idempotency_key=?", (key,))
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

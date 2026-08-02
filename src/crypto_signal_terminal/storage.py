from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet


class AuditStore:
    def __init__(self, path: str | Path, *, encryption_key: bytes | None = None) -> None:
        self.path = Path(path)
        self._fernet = Fernet(encryption_key or self.generate_key())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._migrate_plaintext_table()
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_message_versions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              account_id TEXT NOT NULL,
              channel_id INTEGER NOT NULL,
              message_id INTEGER NOT NULL,
              version_hash TEXT NOT NULL,
              observed_at TEXT NOT NULL,
              deleted INTEGER NOT NULL DEFAULT 0,
              UNIQUE(account_id, channel_id, message_id, version_hash)
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_message_content (
              version_hash TEXT PRIMARY KEY,
              encrypted_raw_text BLOB NOT NULL
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
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS telegram_channel_offsets (
              account_id TEXT NOT NULL,
              channel_id INTEGER NOT NULL,
              last_message_id INTEGER NOT NULL,
              PRIMARY KEY(account_id, channel_id)
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS paper_orders (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id TEXT NOT NULL UNIQUE,
              prepared_at TEXT NOT NULL,
              payload_json TEXT NOT NULL
            )"""
        )
        self._connection.commit()

    @staticmethod
    def generate_key() -> bytes:
        return Fernet.generate_key()

    def _migrate_plaintext_table(self) -> None:
        columns = self._connection.execute("PRAGMA table_info(telegram_message_versions)").fetchall()
        if not columns or "raw_text" not in {str(row[1]) for row in columns}:
            return
        rows = self._connection.execute("SELECT * FROM telegram_message_versions ORDER BY id").fetchall()
        self._connection.execute("ALTER TABLE telegram_message_versions RENAME TO telegram_message_versions_plaintext_legacy")
        self._connection.execute(
            """CREATE TABLE telegram_message_versions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              account_id TEXT NOT NULL,
              channel_id INTEGER NOT NULL,
              message_id INTEGER NOT NULL,
              version_hash TEXT NOT NULL,
              observed_at TEXT NOT NULL,
              deleted INTEGER NOT NULL DEFAULT 0,
              UNIQUE(account_id, channel_id, message_id, version_hash)
            )"""
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS telegram_message_content (
              version_hash TEXT PRIMARY KEY,
              encrypted_raw_text BLOB NOT NULL
            )"""
        )
        for row in rows:
            self._connection.execute(
                """INSERT INTO telegram_message_versions
                   (id, account_id, channel_id, message_id, version_hash, observed_at, deleted)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["account_id"], row["channel_id"], row["message_id"], row["version_hash"], row["observed_at"], row["deleted"]),
            )
            if row["raw_text"] is not None:
                encrypted = self._fernet.encrypt(str(row["raw_text"]).encode("utf-8"))
                self._connection.execute(
                    "INSERT OR IGNORE INTO telegram_message_content (version_hash, encrypted_raw_text) VALUES (?, ?)",
                    (row["version_hash"], encrypted),
                )
        self._connection.execute("DROP TABLE telegram_message_versions_plaintext_legacy")
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
               (account_id, channel_id, message_id, version_hash, observed_at, deleted)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (account_id, channel_id, message_id, version_hash, observed_at.isoformat()),
        )
        if cursor.rowcount == 1:
            encrypted = self._fernet.encrypt(raw_text.encode("utf-8"))
            self._connection.execute(
                "INSERT OR IGNORE INTO telegram_message_content (version_hash, encrypted_raw_text) VALUES (?, ?)",
                (version_hash, encrypted),
            )
        self._connection.commit()
        return cursor.rowcount == 1

    def mark_message_deleted(self, account_id: str, channel_id: int, message_id: int, observed_at: datetime) -> bool:
        marker = f"deleted:{observed_at.isoformat()}"
        version_hash = hashlib.sha256(marker.encode("utf-8")).hexdigest()
        cursor = self._connection.execute(
            """INSERT OR IGNORE INTO telegram_message_versions
               (account_id, channel_id, message_id, version_hash, observed_at, deleted)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (account_id, channel_id, message_id, version_hash, observed_at.isoformat()),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def update_channel_offset(self, account_id: str, channel_id: int, message_id: int) -> None:
        self._connection.execute(
            """INSERT INTO telegram_channel_offsets (account_id, channel_id, last_message_id)
               VALUES (?, ?, ?)
               ON CONFLICT(account_id, channel_id) DO UPDATE SET
               last_message_id=MAX(last_message_id, excluded.last_message_id)""",
            (account_id, channel_id, message_id),
        )
        self._connection.commit()

    def channel_offset(self, account_id: str, channel_id: int) -> int:
        row = self._connection.execute(
            "SELECT last_message_id FROM telegram_channel_offsets WHERE account_id=? AND channel_id=?",
            (account_id, channel_id),
        ).fetchone()
        return int(row[0]) if row else 0

    def message_versions(self, account_id: str, channel_id: int, message_id: int) -> list[dict]:
        rows = self._connection.execute(
            """SELECT c.encrypted_raw_text, v.observed_at, v.deleted, v.version_hash
               FROM telegram_message_versions v
               LEFT JOIN telegram_message_content c ON c.version_hash=v.version_hash
               WHERE account_id=? AND channel_id=? AND message_id=? ORDER BY id""",
            (account_id, channel_id, message_id),
        ).fetchall()
        return [
            {
                "raw_text": self._fernet.decrypt(row["encrypted_raw_text"]).decode("utf-8") if row["encrypted_raw_text"] else None,
                "observed_at": row["observed_at"],
                "deleted": row["deleted"],
                "version_hash": row["version_hash"],
            }
            for row in rows
        ]

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

    def record_paper_order(self, record: dict) -> None:
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        self._connection.execute(
            "INSERT INTO paper_orders (order_id, prepared_at, payload_json) VALUES (?, ?, ?)",
            (record["id"], record["prepared_at"], payload),
        )
        self._connection.commit()

    def paper_orders(self, *, limit: int = 50) -> list[dict]:
        bounded = max(1, min(200, limit))
        rows = self._connection.execute(
            "SELECT payload_json FROM paper_orders ORDER BY prepared_at DESC, sequence DESC LIMIT ?",
            (bounded,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def close(self) -> None:
        self._connection.close()

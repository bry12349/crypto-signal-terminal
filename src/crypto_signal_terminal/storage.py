from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class AuditStore:
    """Local persistence for paper-order history only.

    v0.3 retires the message-ingestion audit database along with the Telegram
    feature. Existing retired tables are dropped at startup so obsolete message
    history cannot be interpreted as an active signal source.
    """

    _RETIRED_TABLES = (
        "telegram_message_versions",
        "telegram_message_content",
        "telegram_channel_offsets",
        "telegram_message_versions_plaintext_legacy",
        "notification_deliveries",
    )

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._retire_message_tables()
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS paper_orders (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              order_id TEXT NOT NULL UNIQUE,
              prepared_at TEXT NOT NULL,
              payload_json TEXT NOT NULL
            )"""
        )
        self._connection.commit()

    def _retire_message_tables(self) -> None:
        for table in self._RETIRED_TABLES:
            self._connection.execute(f'DROP TABLE IF EXISTS "{table}"')

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

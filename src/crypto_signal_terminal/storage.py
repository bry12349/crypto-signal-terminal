from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from crypto_signal_terminal.domain.models import Direction
from crypto_signal_terminal.engines.signal_ledger import SignalRecord
from crypto_signal_terminal.engines.signal_ledger import SignalOutcome


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
    _CALIBRATION_WINDOW = 200

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
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS signal_records (
              signal_id TEXT PRIMARY KEY,
              generated_at TEXT NOT NULL,
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

    def upsert_signal_record(self, record: SignalRecord) -> None:
        payload = json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":"))
        self._connection.execute(
            """INSERT INTO signal_records (signal_id, generated_at, payload_json)
               VALUES (?, ?, ?)
               ON CONFLICT(signal_id) DO UPDATE SET payload_json=excluded.payload_json""",
            (record.signal_id, record.generated_at.isoformat(), payload),
        )
        self._connection.commit()

    def signal_records(self, *, limit: int = 1_000) -> list[SignalRecord]:
        bounded = max(1, min(10_000, limit))
        rows = self._connection.execute(
            "SELECT payload_json FROM signal_records ORDER BY generated_at DESC LIMIT ?", (bounded,),
        ).fetchall()
        return [SignalRecord.from_dict(json.loads(row["payload_json"])) for row in rows]

    def calibration_state(self, *, signal_type: str | None = None, direction: Direction | None = None, symbol: str | None = None) -> dict:
        records = self.signal_records(limit=10_000)
        settled = [
            record for record in records
            if record.outcome in {SignalOutcome.TP1, SignalOutcome.STOP}
            and record.predicted_probability is not None
            and (signal_type is None or record.signal_type == signal_type)
            and (direction is None or record.plan.direction == direction)
            and (symbol is None or record.symbol == symbol)
        ][:self._CALIBRATION_WINDOW]
        if settled:
            mean_predicted = sum((record.predicted_probability or Decimal("0") for record in settled), Decimal("0")) / len(settled)
            observed_win_rate = Decimal(sum(record.outcome is SignalOutcome.TP1 for record in settled)) / len(settled)
            brier_score = sum((
                ((record.predicted_probability or Decimal("0")) - Decimal(record.outcome is SignalOutcome.TP1)) ** 2
                for record in settled
            ), Decimal("0")) / len(settled)
        else:
            mean_predicted = Decimal("0")
            observed_win_rate = Decimal("0")
            brier_score = Decimal("0")
        absolute_error = abs(mean_predicted - observed_win_rate)
        status = "INSUFFICIENT" if len(settled) < 30 else (
            "VALIDATED" if absolute_error <= Decimal("0.12") and brier_score <= Decimal("0.25") else "DEGRADED"
        )
        return {
            "settled": len(settled),
            "mean_predicted": float(mean_predicted),
            "observed_win_rate": float(observed_win_rate),
            "absolute_error": float(absolute_error),
            "brier_score": float(brier_score),
            "status": status,
        }

    def signal_performance(self) -> dict:
        records = self.signal_records(limit=10_000)
        settled = [record for record in records if record.outcome in {SignalOutcome.TP1, SignalOutcome.STOP}]
        wins = sum(record.outcome is SignalOutcome.TP1 for record in settled)
        buckets: dict[int, list[SignalRecord]] = {}
        for record in settled:
            if record.predicted_probability is None:
                continue
            bucket = min(9, int(record.predicted_probability * 10))
            buckets.setdefault(bucket, []).append(record)
        calibration = [
            {
                "bucket": f"{bucket / 10:.1f}-{(bucket + 1) / 10:.1f}",
                "count": len(items),
                "predicted": float(sum(item.predicted_probability or 0 for item in items) / len(items)),
                "observed": sum(item.outcome is SignalOutcome.TP1 for item in items) / len(items),
            }
            for bucket, items in sorted(buckets.items())
        ]
        return {
            "total": len(records),
            "settled": len(settled),
            "wins": wins,
            "losses": len(settled) - wins,
            "ambiguous": sum(record.outcome is SignalOutcome.AMBIGUOUS for record in records),
            "unfilled": sum(record.outcome is SignalOutcome.EXPIRED_UNFILLED for record in records),
            "win_rate": wins / len(settled) if settled else 0.0,
            "calibration": calibration,
            "calibration_state": self.calibration_state(),
        }

    def close(self) -> None:
        self._connection.close()

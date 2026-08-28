"""Deterministic, conservative settlement for emitted trade signals.

This module deliberately refuses to infer the intra-candle price path.  A bar
that crosses both stop and target is excluded as ambiguous rather than counted
as a convenient winner or loser in later calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from crypto_signal_terminal.domain.models import Candle, OrderPlan, OrderType


class SignalOutcome(StrEnum):
    PENDING = "PENDING"
    TP1 = "TP1"
    STOP = "STOP"
    EXPIRED_UNFILLED = "EXPIRED_UNFILLED"
    EXPIRED_FILLED = "EXPIRED_FILLED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class SignalRecord:
    signal_id: str
    symbol: str
    plan: OrderPlan
    generated_at: datetime
    predicted_probability: Decimal | None = None
    expected_value: Decimal | None = None
    market_regime: str | None = None
    signal_type: str | None = None
    outcome: SignalOutcome = SignalOutcome.PENDING
    entry_price: Decimal | None = None
    settled_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "plan": self.plan.model_dump(mode="json"),
            "generated_at": self.generated_at.isoformat(),
            "predicted_probability": str(self.predicted_probability) if self.predicted_probability is not None else None,
            "expected_value": str(self.expected_value) if self.expected_value is not None else None,
            "market_regime": self.market_regime,
            "signal_type": self.signal_type,
            "outcome": self.outcome.value,
            "entry_price": str(self.entry_price) if self.entry_price is not None else None,
            "settled_at": self.settled_at.isoformat() if self.settled_at is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "SignalRecord":
        return cls(
            signal_id=payload["signal_id"],
            symbol=payload["symbol"],
            plan=OrderPlan.model_validate(payload["plan"]),
            generated_at=datetime.fromisoformat(payload["generated_at"]),
            predicted_probability=Decimal(payload["predicted_probability"]) if payload.get("predicted_probability") is not None else None,
            expected_value=Decimal(payload["expected_value"]) if payload.get("expected_value") is not None else None,
            market_regime=payload.get("market_regime"),
            signal_type=payload.get("signal_type"),
            outcome=SignalOutcome(payload["outcome"]),
            entry_price=Decimal(payload["entry_price"]) if payload.get("entry_price") is not None else None,
            settled_at=datetime.fromisoformat(payload["settled_at"]) if payload.get("settled_at") else None,
        )


def _bar_time(candle: Candle) -> datetime:
    return datetime.fromtimestamp(candle.timestamp, tz=UTC)


def _limit_was_filled(plan: OrderPlan, candle: Candle) -> bool:
    return candle.low <= plan.entry_high and candle.high >= plan.entry_low


def _target_and_stop_hit(record: SignalRecord, candle: Candle) -> tuple[bool, bool]:
    if record.plan.direction.value == "LONG":
        return candle.high >= record.plan.targets[0], candle.low <= record.plan.stop
    return candle.low <= record.plan.targets[0], candle.high >= record.plan.stop


def settle_signal(record: SignalRecord, candles: list[Candle] | tuple[Candle, ...], *, now: datetime) -> SignalRecord:
    """Return the next immutable state of a signal from verified OHLCV bars."""
    if record.outcome is not SignalOutcome.PENDING:
        return record

    entered_at = record.entry_price
    for candle in sorted(candles, key=lambda item: item.timestamp):
        candle_time = _bar_time(candle)
        if candle_time < record.generated_at or candle_time > record.plan.expires_at:
            continue
        if entered_at is None:
            if record.plan.order_type is OrderType.LIMIT:
                if not _limit_was_filled(record.plan, candle):
                    continue
                entered_at = (record.plan.entry_low + record.plan.entry_high) / Decimal("2")
            else:
                entered_at = record.plan.entry_high
        entered = replace(record, entry_price=entered_at)
        target_hit, stop_hit = _target_and_stop_hit(entered, candle)
        if target_hit and stop_hit:
            return replace(entered, outcome=SignalOutcome.AMBIGUOUS, settled_at=candle_time)
        if target_hit:
            return replace(entered, outcome=SignalOutcome.TP1, settled_at=candle_time)
        if stop_hit:
            return replace(entered, outcome=SignalOutcome.STOP, settled_at=candle_time)

    if now > record.plan.expires_at:
        return replace(
            record,
            entry_price=entered_at,
            outcome=SignalOutcome.EXPIRED_FILLED if entered_at is not None else SignalOutcome.EXPIRED_UNFILLED,
            settled_at=record.plan.expires_at,
        )
    return replace(record, entry_price=entered_at)

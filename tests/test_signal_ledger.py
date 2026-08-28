from datetime import UTC, datetime, timedelta
from decimal import Decimal

from crypto_signal_terminal.domain.models import Candle, Direction, OrderPlan, OrderType
from crypto_signal_terminal.engines.signal_ledger import SignalOutcome, SignalRecord, settle_signal
from crypto_signal_terminal.storage import AuditStore


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def long_plan(*, order_type: OrderType = OrderType.MARKET) -> OrderPlan:
    return OrderPlan(
        direction=Direction.LONG,
        order_type=order_type,
        entry_low=Decimal("100"),
        entry_high=Decimal("101"),
        stop=Decimal("98"),
        targets=(Decimal("104"), Decimal("107")),
        target_allocations=(Decimal("0.5"), Decimal("0.5")),
        expires_at=NOW + timedelta(minutes=5),
        max_slippage_bps=Decimal("10"),
        suggested_quantity=Decimal("10"),
        risk_amount=Decimal("25"),
        reward_to_risk=Decimal("2"),
        invalidation="5m close below 98",
    )


def test_ledger_settles_first_target_before_stop() -> None:
    record = SignalRecord(signal_id="trend:btc:1", symbol="BTCUSDT", plan=long_plan(), generated_at=NOW)
    outcome = settle_signal(record, [
        Candle(timestamp=int((NOW + timedelta(minutes=1)).timestamp()), open="101", high="104.2", low="100", close="104", volume="10"),
    ], now=NOW + timedelta(minutes=1))

    assert outcome.outcome is SignalOutcome.TP1
    assert outcome.settled_at == NOW + timedelta(minutes=1)


def test_ledger_marks_same_candle_stop_and_target_as_ambiguous() -> None:
    record = SignalRecord(signal_id="trend:btc:2", symbol="BTCUSDT", plan=long_plan(), generated_at=NOW)
    outcome = settle_signal(record, [
        Candle(timestamp=int((NOW + timedelta(minutes=1)).timestamp()), open="101", high="104.5", low="97.5", close="101", volume="10"),
    ], now=NOW + timedelta(minutes=1))

    assert outcome.outcome is SignalOutcome.AMBIGUOUS


def test_ledger_expires_unfilled_limit_signal_without_inventing_entry() -> None:
    record = SignalRecord(signal_id="trend:btc:3", symbol="BTCUSDT", plan=long_plan(order_type=OrderType.LIMIT), generated_at=NOW)
    outcome = settle_signal(record, [
        Candle(timestamp=int((NOW + timedelta(minutes=1)).timestamp()), open="105", high="106", low="104", close="105", volume="10"),
    ], now=NOW + timedelta(minutes=6))

    assert outcome.outcome is SignalOutcome.EXPIRED_UNFILLED
    assert outcome.entry_price is None


def test_ledger_persists_the_latest_outcome_for_calibration(tmp_path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    record = SignalRecord(signal_id="trend:btc:4", symbol="BTCUSDT", plan=long_plan(), generated_at=NOW)
    store.upsert_signal_record(settle_signal(record, [
        Candle(timestamp=int((NOW + timedelta(minutes=1)).timestamp()), open="101", high="104.2", low="100", close="104", volume="10"),
    ], now=NOW + timedelta(minutes=1)))

    loaded = store.signal_records()

    assert loaded[0].signal_id == "trend:btc:4"
    assert loaded[0].outcome is SignalOutcome.TP1

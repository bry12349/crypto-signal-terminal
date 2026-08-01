from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_signal_terminal.market.features import calculate_features
from crypto_signal_terminal.market.state import MarketEvent, MarketState, StaleMarketData


NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def event(kind: str, *, sequence: int | None = None, **payload: str) -> MarketEvent:
    return MarketEvent(
        exchange="binance",
        symbol="BTCUSDT",
        kind=kind,
        exchange_time=NOW,
        received_at=NOW,
        sequence=sequence,
        payload=payload,
    )


def test_sequence_gap_marks_book_unhealthy_until_snapshot() -> None:
    state = MarketState(stale_after=timedelta(seconds=5))
    state.apply(event("book_snapshot", sequence=10, bid="100", ask="101", bid_size="5", ask_size="4"))
    state.apply(event("book_delta", sequence=12, bid="100", ask="101", bid_size="6", ask_size="4"))
    assert state.health("BTCUSDT", NOW).healthy is False
    assert "book_sequence_gap" in state.health("BTCUSDT", NOW).stale_sources

    state.apply(event("book_snapshot", sequence=20, bid="100", ask="101", bid_size="7", ask_size="3"))
    assert "book_sequence_gap" not in state.health("BTCUSDT", NOW).stale_sources


def test_snapshot_rejects_stale_trade_data() -> None:
    state = MarketState(stale_after=timedelta(seconds=5))
    state.apply(event("ticker", price="100", bid="99.9", ask="100.1"))
    state.apply(event("open_interest", value="1000000"))
    with pytest.raises(StaleMarketData, match="stale"):
        state.snapshot("BTCUSDT", NOW + timedelta(seconds=6))


def test_snapshot_contains_spread_and_depth_features() -> None:
    state = MarketState(stale_after=timedelta(seconds=5))
    state.apply(event("ticker", price="100", bid="99", ask="101"))
    state.apply(event("open_interest", value="1000000"))
    state.apply(event("book_snapshot", sequence=1, bid="99", ask="101", bid_size="8", ask_size="2"))
    snapshot = state.snapshot("BTCUSDT", NOW)
    features = calculate_features(snapshot)
    assert features.spread_bps == Decimal("200")
    assert features.depth_imbalance == Decimal("0.6")


def test_trade_flow_builds_aggressive_imbalance() -> None:
    state = MarketState(stale_after=timedelta(seconds=5))
    state.apply(event("ticker", price="100", bid="99.9", ask="100.1"))
    state.apply(event("open_interest", value="1000000"))
    state.apply(event("trade", side="BUY", price="100", size="8"))
    state.apply(event("trade", side="SELL", price="100", size="2"))
    features = calculate_features(state.snapshot("BTCUSDT", NOW))
    assert features.aggressive_flow_imbalance == Decimal("0.6")

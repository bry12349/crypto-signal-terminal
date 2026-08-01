from datetime import UTC, datetime
from decimal import Decimal

from crypto_signal_terminal.domain.models import DataHealth, LifecycleState, MarketSnapshot, OrderType
from crypto_signal_terminal.engines.altcoin import AltcoinEngine
from crypto_signal_terminal.engines.trend import TrendEngine


NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def snapshot(symbol: str = "BTCUSDT", **features) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        exchange="composite",
        observed_at=NOW,
        price=Decimal("100"),
        bid=Decimal("99.95"),
        ask=Decimal("100.05"),
        open_interest=Decimal("1000000"),
        funding_rate=Decimal("0.0001"),
        volume_24h=Decimal("100000000"),
        data_health=DataHealth(healthy=True, observed_at=NOW),
        peer_confirmations=3,
        features=features,
    )


def test_trend_pullback_is_armed_not_chased() -> None:
    result = TrendEngine().evaluate(
        snapshot(trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=0, atr_percentile=55)
    )
    assert result is not None
    assert result.state is LifecycleState.ARMED
    assert result.order_plan is None


def test_trend_trigger_produces_limit_or_market_plan() -> None:
    result = TrendEngine().evaluate(
        snapshot(trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1, aggressive_flow_imbalance="0.55")
    )
    assert result is not None
    assert result.state is LifecycleState.ENTRY_VALID
    assert result.order_plan is not None
    assert result.order_plan.order_type in {OrderType.MARKET, OrderType.LIMIT}


def test_trend_engine_does_not_trade_conflicting_timeframes() -> None:
    result = TrendEngine().evaluate(snapshot(trend_4h=1, trend_1h=-1, setup_15m=1, trigger_5m=1))
    assert result is None


def test_altcoin_compression_without_trigger_is_forming() -> None:
    result = AltcoinEngine().evaluate(
        snapshot(
            symbol="SOLUSDT",
            atr_percentile=12,
            volume_acceleration="1.8",
            oi_change_ratio="0.05",
            aggressive_flow_imbalance="0.45",
            depth_imbalance="0.3",
            trigger_5m=0,
            spread_bps="6",
        )
    )
    assert result is not None
    assert result.state is LifecycleState.ARMED


def test_altcoin_trigger_requires_cross_exchange_confirmation() -> None:
    base = snapshot(
        symbol="SUIUSDT",
        atr_percentile=10,
        volume_acceleration="2.2",
        oi_change_ratio="0.08",
        aggressive_flow_imbalance="-0.6",
        depth_imbalance="-0.45",
        trigger_5m=-1,
        spread_bps="8",
    )
    unconfirmed = base.model_copy(update={"peer_confirmations": 1})
    confirmed = base.model_copy(update={"peer_confirmations": 3})
    assert AltcoinEngine().evaluate(unconfirmed).state is LifecycleState.ARMED
    assert AltcoinEngine().evaluate(confirmed).state is LifecycleState.ENTRY_VALID


def test_altcoin_illiquid_contract_is_excluded() -> None:
    result = AltcoinEngine(max_spread_bps=Decimal("20")).evaluate(
        snapshot(symbol="TINYUSDT", atr_percentile=8, volume_acceleration="3", oi_change_ratio="0.1", spread_bps="45")
    )
    assert result is None

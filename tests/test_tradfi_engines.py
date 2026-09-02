from datetime import UTC, datetime
from decimal import Decimal

import pytest

from crypto_signal_terminal.domain.models import AssetClass, DataHealth, Direction, LifecycleState, MarketSnapshot
from crypto_signal_terminal.engines.commodity import CommodityEngine
from crypto_signal_terminal.engines.equity import EquityEngine
from crypto_signal_terminal.market.instruments import asset_class_for_symbol


NOW = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)


def snapshot(symbol: str, asset_class: AssetClass, **features: str | int | bool) -> MarketSnapshot:
    price = Decimal("100")
    return MarketSnapshot(
        symbol=symbol,
        asset_class=asset_class,
        exchange="bybit-public-composite",
        observed_at=NOW,
        price=price,
        bid=Decimal("99.98"),
        ask=Decimal("100.02"),
        open_interest=Decimal("100000"),
        volume_24h=Decimal("100000000"),
        data_health=DataHealth(healthy=True, observed_at=NOW, latency_ms=100),
        peer_confirmations=2,
        features=features,
    )


def test_instrument_classification_keeps_contract_families_separate() -> None:
    assert asset_class_for_symbol("BTCUSDT") is AssetClass.CRYPTO
    assert asset_class_for_symbol("XAUUSDT") is AssetClass.COMMODITY
    assert asset_class_for_symbol("TSLAUSDT") is AssetClass.US_EQUITY


def test_commodity_engine_blocks_event_risk_and_does_not_use_crypto_funding() -> None:
    setup = snapshot(
        "XAUUSDT", AssetClass.COMMODITY,
        trend_1d=1, trend_4h=1, trend_1h=1, trigger_5m=1,
        macro_score="0.7", term_structure_score="0.4", commodity_flow="0.6",
        atr_percentile="48", volume_acceleration="1.8", session_liquidity="0.9",
        event_risk="0.9", spread_bps="2", slippage_bps_1000="2",
        funding_rate="-0.5",  # Must not turn this into a crypto signal.
    )
    assert CommodityEngine().evaluate(setup) is None


def test_commodity_engine_requires_independent_macro_structure_and_emits_profile() -> None:
    setup = snapshot(
        "XAUUSDT", AssetClass.COMMODITY,
        trend_1d=1, trend_4h=1, trend_1h=1, trigger_5m=1,
        macro_score="0.72", term_structure_score="0.35", commodity_flow="0.62",
        atr_percentile="48", volume_acceleration="1.8", session_liquidity="0.9",
        event_risk="0.1", spread_bps="2", slippage_bps_1000="2",
        risk_reward="2.0",
    )
    result = CommodityEngine().evaluate(setup)
    assert result is not None
    assert result.state is LifecycleState.ENTRY_VALID
    assert result.analysis is not None
    assert result.analysis.asset_profile == "COMMODITY"
    assert result.analysis.signal_type == "commodity_macro"


def test_equity_engine_blocks_earnings_and_overnight_gap_risk() -> None:
    setup = snapshot(
        "TSLAUSDT", AssetClass.US_EQUITY,
        trend_4h=1, trend_1h=1, trigger_5m=1, index_regime=1,
        relative_strength="0.7", equity_flow="0.6", atr_percentile="45",
        volume_acceleration="1.7", session_liquidity="0.9", earnings_risk="0.8",
        gap_risk="0.8", spread_bps="2", slippage_bps_1000="2",
    )
    assert EquityEngine().evaluate(setup) is None


def test_equity_engine_emits_separate_market_model() -> None:
    setup = snapshot(
        "TSLAUSDT", AssetClass.US_EQUITY,
        trend_4h=1, trend_1h=1, trigger_5m=1, index_regime=1,
        relative_strength="0.7", equity_flow="0.6", atr_percentile="45",
        volume_acceleration="1.7", session_liquidity="0.9", earnings_risk="0.1",
        gap_risk="0.1", spread_bps="2", slippage_bps_1000="2",
        risk_reward="2.0",
    )
    result = EquityEngine().evaluate(setup)
    assert result is not None
    assert result.analysis is not None
    assert result.analysis.asset_profile == "US_EQUITY"
    assert result.analysis.signal_type == "equity_relative_strength"


@pytest.mark.parametrize("asset_class", [AssetClass.COMMODITY, AssetClass.US_EQUITY])
def test_wrong_engine_never_evaluates_another_asset_class(asset_class: AssetClass) -> None:
    symbol = "XAUUSDT" if asset_class is AssetClass.COMMODITY else "TSLAUSDT"
    other = AssetClass.US_EQUITY if asset_class is AssetClass.COMMODITY else AssetClass.COMMODITY
    assert CommodityEngine().evaluate(snapshot(symbol, other)) is None
    assert EquityEngine().evaluate(snapshot(symbol, other)) is None

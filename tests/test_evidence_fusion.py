from datetime import UTC, datetime
from decimal import Decimal

from crypto_signal_terminal.domain.models import CalibrationState, DataHealth, Direction, MarketSnapshot
from crypto_signal_terminal.engines.evidence_fusion import EvidenceFusion


NOW = datetime(2026, 8, 27, 18, 0, tzinfo=UTC)


def market(**features: object) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="ETHUSDT",
        exchange="bybit",
        observed_at=NOW,
        price=Decimal("4200"),
        bid=Decimal("4199.8"),
        ask=Decimal("4200.2"),
        open_interest=Decimal("10000000"),
        funding_rate=Decimal("0.0001"),
        volume_24h=Decimal("500000000"),
        data_health=DataHealth(healthy=True, observed_at=NOW),
        peer_confirmations=3,
        features=features,
    )


def test_fusion_allows_high_alignment_positive_expectancy() -> None:
    analysis = EvidenceFusion().evaluate(
        market(
            trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1,
            aggressive_flow_imbalance="0.72", depth_imbalance="0.44",
            flow_persistence="0.92", oi_change_ratio="0.07",
            volume_acceleration="2.2", atr_percentile="18", price_impact_bps="14",
        ),
        direction=Direction.LONG,
        reward_to_risk=Decimal("1.8"),
        signal_type="trend_continuation",
    )
    assert analysis.is_tradeable is True
    assert analysis.p_tp_before_sl > Decimal("0.56")
    assert analysis.expected_value > 0
    assert analysis.news_bias == "UNAVAILABLE"
    assert analysis.smart_money_bias == "UNAVAILABLE"
    assert analysis.decision.outcome == "TRADE"
    assert all(gate.passed for gate in analysis.decision.gates)


def test_fusion_rejects_conflicting_low_edge_setup() -> None:
    analysis = EvidenceFusion().evaluate(
        market(
            trend_4h=1, trend_1h=-1, setup_15m=1, trigger_5m=-1,
            aggressive_flow_imbalance="-0.38", depth_imbalance="0.15",
            flow_persistence="0.40", oi_change_ratio="-0.02",
            volume_acceleration="0.8", atr_percentile="82", price_impact_bps="-4",
        ),
        direction=Direction.LONG,
        reward_to_risk=Decimal("1.1"),
        signal_type="trend_continuation",
    )
    assert analysis.is_tradeable is False
    assert analysis.evidence_conflict >= Decimal("0.30")
    assert analysis.expected_value <= 0
    assert analysis.decision.outcome == "NO_TRADE"
    assert any(gate.key == "expected_value" and not gate.passed for gate in analysis.decision.gates)


def test_fusion_blocks_trade_when_a_sufficient_history_shows_the_model_is_miscalibrated() -> None:
    analysis = EvidenceFusion().evaluate(
        market(
            trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1,
            aggressive_flow_imbalance="0.72", depth_imbalance="0.44",
            flow_persistence="0.92", oi_change_ratio="0.07",
            volume_acceleration="2.2", atr_percentile="18", price_impact_bps="14",
        ),
        direction=Direction.LONG,
        reward_to_risk=Decimal("1.8"),
        signal_type="trend_continuation",
        calibration=CalibrationState(
            settled=30, mean_predicted=Decimal("0.68"), observed_win_rate=Decimal("0.48"),
            absolute_error=Decimal("0.20"), status="DEGRADED",
        ),
    )

    assert analysis.is_tradeable is False
    assert analysis.decision.outcome == "NO_TRADE"
    assert any(gate.key == "historical_calibration" and not gate.passed for gate in analysis.decision.gates)


def test_fusion_only_labels_public_onchain_wallet_flow_as_smart_money() -> None:
    analysis = EvidenceFusion().evaluate(
        market(
            trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1,
            aggressive_flow_imbalance="0.72", depth_imbalance="0.44",
            flow_persistence="0.92", oi_change_ratio="0.07",
            volume_acceleration="2.2", atr_percentile="18", price_impact_bps="14",
            smart_money_source="public_onchain_wallet", onchain_smart_money_flow="0.75",
        ),
        direction=Direction.LONG,
        reward_to_risk=Decimal("1.8"),
        signal_type="trend_continuation",
    )

    assert analysis.smart_money_bias == "BULLISH"


def test_fusion_uses_distinct_btc_and_altcoin_profiles() -> None:
    shared = dict(
        trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1,
        aggressive_flow_imbalance="0.45", depth_imbalance="0.25",
        flow_persistence="0.8", oi_change_ratio="0.05",
        volume_acceleration="1.8", atr_percentile="25", price_impact_bps="8",
        btc_cycle_bias="1", btc_regime_score="1",
        narrative_score="-0.30", narrative_bias="BEARISH", narrative_independent_sources=3,
    )
    btc = market(**shared).model_copy(update={"symbol": "BTCUSDT"})
    alt = market(**shared).model_copy(update={"symbol": "SOLUSDT"})

    btc_analysis = EvidenceFusion().evaluate(
        btc, direction=Direction.LONG, reward_to_risk=Decimal("1.8"), signal_type="trend_continuation",
    )
    alt_analysis = EvidenceFusion().evaluate(
        alt, direction=Direction.LONG, reward_to_risk=Decimal("1.8"), signal_type="volatility_expansion",
    )

    assert btc_analysis.asset_profile == "BTC"
    assert alt_analysis.asset_profile == "ALT"
    assert btc_analysis.model_version == "0.7.0"
    assert btc_analysis.opportunity_score != alt_analysis.opportunity_score
    assert btc_analysis.narrative_bias == "BEARISH"


def test_unconfirmed_narrative_cannot_change_the_directional_score() -> None:
    base = dict(
        trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1,
        aggressive_flow_imbalance="0.72", depth_imbalance="0.44",
        flow_persistence="0.92", oi_change_ratio="0.07",
        volume_acceleration="2.2", atr_percentile="18", price_impact_bps="14",
    )
    without = EvidenceFusion().evaluate(
        market(**base), direction=Direction.LONG, reward_to_risk=Decimal("1.8"), signal_type="trend_continuation",
    )
    with_one_source = EvidenceFusion().evaluate(
        market(**base, narrative_score="-0.35", narrative_bias="UNCONFIRMED", narrative_independent_sources=1),
        direction=Direction.LONG, reward_to_risk=Decimal("1.8"), signal_type="trend_continuation",
    )

    assert without.p_tp_before_sl == with_one_source.p_tp_before_sl

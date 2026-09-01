from datetime import UTC, datetime
from decimal import Decimal

from crypto_signal_terminal.domain.models import DataHealth, Direction, MarketSnapshot
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

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_signal_terminal.adapters.dune import DuneAdapter, DuneConfigurationError
from crypto_signal_terminal.domain.models import DataHealth, Direction, MarketSnapshot, SmartMoneyKind
from crypto_signal_terminal.engines.smart_money import SmartMoneyEngine, WalletObservation, score_wallet


NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def flow_snapshot(**features) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="SOLUSDT",
        exchange="composite",
        observed_at=NOW,
        price=Decimal("150"),
        bid=Decimal("149.9"),
        ask=Decimal("150.1"),
        open_interest=Decimal("900000"),
        data_health=DataHealth(healthy=True, observed_at=NOW),
        peer_confirmations=3,
        features=features,
    )


def test_single_large_trade_is_not_smart_money() -> None:
    candidate = SmartMoneyEngine().evaluate_flow(
        flow_snapshot(large_trade_count=1, flow_persistence="0.2", aggressive_flow_imbalance="0.8", oi_change_ratio="0.1")
    )
    assert candidate is None


def test_persistent_flow_with_oi_produces_candidate() -> None:
    candidate = SmartMoneyEngine().evaluate_flow(
        flow_snapshot(
            large_trade_count=7,
            flow_persistence="0.82",
            aggressive_flow_imbalance="0.7",
            oi_change_ratio="0.08",
            price_impact_bps="18",
            absorption="0.1",
        )
    )
    assert candidate is not None
    assert candidate.kind is SmartMoneyKind.DERIVATIVES_FLOW
    assert candidate.direction is Direction.LONG


def test_wallet_score_ignores_future_outcomes() -> None:
    history = [
        WalletObservation(wallet="0xabc", chain="ethereum", timestamp=NOW - timedelta(days=2), realized_return=Decimal("0.1"), max_drawdown=Decimal("0.02"), token="ETH"),
        WalletObservation(wallet="0xabc", chain="ethereum", timestamp=NOW + timedelta(days=1), realized_return=Decimal("1.0"), max_drawdown=Decimal("0.01"), token="SOL"),
    ]
    early = score_wallet(history, as_of=NOW)
    late = score_wallet(history, as_of=NOW + timedelta(days=2))
    assert late.score > early.score
    assert early.observation_count == 1


@pytest.mark.asyncio
async def test_dune_adapter_disables_without_key() -> None:
    adapter = DuneAdapter(api_key=None, query_id=None)
    with pytest.raises(DuneConfigurationError, match="not configured"):
        await adapter.latest_rows()


def test_dune_row_validation() -> None:
    adapter = DuneAdapter(api_key="redacted", query_id=123)
    rows = adapter.parse_rows([
        {"wallet": "0xabc", "chain": "ethereum", "token": "ETH", "side": "BUY", "value_usd": "100000", "timestamp": "2026-08-01T08:00:00Z", "tx_hash": "0x1", "realized_return": "0.12", "max_drawdown": "0.03"}
    ])
    assert rows[0].wallet == "0xabc"
    assert rows[0].realized_return == Decimal("0.12")

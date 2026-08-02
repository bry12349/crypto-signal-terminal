from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from crypto_signal_terminal.confirmation import ConfirmationEngine
from crypto_signal_terminal.domain.models import (
    DataHealth,
    Direction,
    MarketSnapshot,
    OrderType,
    TelegramSignal,
    Verdict,
)
from crypto_signal_terminal.order_planner import OrderPlanner, RiskSettings
from crypto_signal_terminal.storage import AuditStore
from crypto_signal_terminal.telegram.notifier import TelegramBotNotifier


NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def signal(**updates) -> TelegramSignal:
    payload = dict(
        account_id="me",
        channel_id=10,
        message_id=20,
        published_at=NOW - timedelta(seconds=10),
        raw_text="SOL short entry 146.2-146.5 sl 147.4 tp 144.6 142.9",
        symbol="SOLUSDT",
        direction=Direction.SHORT,
        entry_low=Decimal("146.2"),
        entry_high=Decimal("146.5"),
        stop=Decimal("147.4"),
        targets=(Decimal("144.6"), Decimal("142.9")),
        parse_confidence=100,
        issues=(),
    )
    payload.update(updates)
    return TelegramSignal(**payload)


def market(*, price: str = "146.35", healthy: bool = True, peer_confirmations: int = 3, funding_rate: str = "0.0001", latency_ms: int = 0, spread: str = "0.02", **features) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="SOLUSDT",
        exchange="composite",
        observed_at=NOW,
        price=Decimal(price),
        bid=Decimal(price) - Decimal(spread),
        ask=Decimal(price) + Decimal(spread),
        open_interest=Decimal("900000"),
        funding_rate=Decimal(funding_rate),
        volume_24h=Decimal("100000000"),
        peer_confirmations=peer_confirmations,
        data_health=DataHealth(healthy=healthy, observed_at=NOW, latency_ms=latency_ms, stale_sources=() if healthy else ("ticker",)),
        features={"spread_bps": "3", "aggressive_flow_imbalance": "-0.65", "oi_change_ratio": "0.07", "trend_1h": -1, **features},
    )


def test_order_planner_uses_fixed_risk_budget() -> None:
    planner = OrderPlanner(RiskSettings(account_equity=Decimal("10000"), risk_fraction=Decimal("0.0025")))
    plan = planner.from_telegram(signal(), market())
    assert plan.risk_amount == Decimal("25.0000")
    assert plan.direction is Direction.SHORT
    assert plan.order_type is OrderType.LIMIT
    assert plan.suggested_quantity > 0
    midpoint = (plan.entry_low + plan.entry_high) / Decimal("2")
    stop_loss = abs(midpoint - plan.stop) * plan.suggested_quantity
    assert stop_loss + plan.estimated_fees < plan.risk_amount


def test_order_planner_rejects_stop_on_wrong_side() -> None:
    planner = OrderPlanner(RiskSettings(account_equity=Decimal("10000"), risk_fraction=Decimal("0.0025")))
    with pytest.raises(ValueError, match="stop"):
        planner.from_telegram(signal(stop=Decimal("145")), market())


def test_chased_signal_becomes_expired() -> None:
    result = ConfirmationEngine().confirm(signal(), market(price="142"), analyzed_at=NOW)
    assert result.verdict is Verdict.EXPIRED
    assert "entry_missed" in result.reason_codes


def test_stale_market_cannot_confirm() -> None:
    result = ConfirmationEngine().confirm(signal(), market(healthy=False), analyzed_at=NOW)
    assert result.verdict is Verdict.REJECTED
    assert "stale_market" in result.reason_codes


def test_incomplete_signal_is_unparseable() -> None:
    result = ConfirmationEngine().confirm(
        signal(direction=None, entry_low=None, entry_high=None, parse_confidence=40, issues=("missing_direction", "missing_entry")),
        market(),
        analyzed_at=NOW,
    )
    assert result.verdict is Verdict.UNPARSEABLE


def test_aligned_signal_is_confirmed_with_recommended_plan() -> None:
    result = ConfirmationEngine().confirm(signal(), market(), analyzed_at=NOW)
    assert result.verdict is Verdict.CONFIRMED
    assert result.order_plan is not None
    assert result.confidence >= 75


@pytest.mark.parametrize(
    ("snapshot", "reason"),
    [
        (market(peer_confirmations=1), None),
        (market(funding_rate="0.004"), "extreme_funding"),
        (market(latency_ms=6000), "market_latency_too_high"),
        (market(spread="0.30"), "spread_too_wide"),
        (market(slippage_bps_1000="22"), "slippage_too_high"),
        (market(depth_imbalance="0.8"), "directional_depth_opposes_signal"),
    ],
)
def test_confirmation_requires_liquid_fresh_cross_checked_market(snapshot: MarketSnapshot, reason: str | None) -> None:
    result = ConfirmationEngine().confirm(signal(), snapshot, analyzed_at=NOW)
    if reason is None:
        assert result.verdict is Verdict.CONDITIONAL
    else:
        assert result.verdict is Verdict.REJECTED
        assert reason in result.reason_codes


@pytest.mark.asyncio
async def test_notifier_deduplicates_delivery(tmp_path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert "botsecret" in str(request.url)
        return httpx.Response(200, json={"ok": True})

    store = AuditStore(tmp_path / "audit.sqlite3")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notifier = TelegramBotNotifier(bot_token="secret", chat_id="123", store=store, client=client)
    result = ConfirmationEngine().confirm(signal(), market(), analyzed_at=NOW)
    assert await notifier.send(result) is True
    assert await notifier.send(result) is False
    assert calls == 1
    await client.aclose()


def test_paper_order_journal_survives_store_restart(tmp_path) -> None:
    path = tmp_path / "audit.sqlite3"
    record = {
        "id": "paper:stable",
        "opportunity_id": "trend:BTCUSDT:entry",
        "symbol": "BTCUSDT",
        "status": "PREPARED",
        "prepared_at": NOW.isoformat(),
        "plan": {"direction": "LONG", "stop": "66000"},
    }
    store = AuditStore(path)
    store.record_paper_order(record)
    store.close()

    reopened = AuditStore(path)
    assert reopened.paper_orders() == [record]


def test_paper_order_history_limit_is_bounded(tmp_path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    for index in range(3):
        store.record_paper_order({
            "id": f"paper:{index}",
            "opportunity_id": f"opportunity:{index}",
            "symbol": "BTCUSDT",
            "status": "PREPARED",
            "prepared_at": (NOW + timedelta(seconds=index)).isoformat(),
            "plan": {"direction": "LONG"},
        })
    assert [item["id"] for item in store.paper_orders(limit=2)] == ["paper:2", "paper:1"]
    assert len(store.paper_orders(limit=500)) == 3

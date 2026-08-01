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


def market(*, price: str = "146.35", healthy: bool = True, **features) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="SOLUSDT",
        exchange="composite",
        observed_at=NOW,
        price=Decimal(price),
        bid=Decimal(price) - Decimal("0.02"),
        ask=Decimal(price) + Decimal("0.02"),
        open_interest=Decimal("900000"),
        funding_rate=Decimal("0.0001"),
        volume_24h=Decimal("100000000"),
        peer_confirmations=3,
        data_health=DataHealth(healthy=healthy, observed_at=NOW, stale_sources=() if healthy else ("ticker",)),
        features={"spread_bps": "3", "aggressive_flow_imbalance": "-0.65", "oi_change_ratio": "0.07", "trend_1h": -1, **features},
    )


def test_order_planner_uses_fixed_risk_budget() -> None:
    planner = OrderPlanner(RiskSettings(account_equity=Decimal("10000"), risk_fraction=Decimal("0.0025")))
    plan = planner.from_telegram(signal(), market())
    assert plan.risk_amount == Decimal("25.0000")
    assert plan.direction is Direction.SHORT
    assert plan.order_type is OrderType.LIMIT
    assert plan.suggested_quantity > 0


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

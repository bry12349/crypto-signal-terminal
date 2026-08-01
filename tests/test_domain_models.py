from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from crypto_signal_terminal.domain.models import (
    DataHealth,
    Direction,
    Evidence,
    LifecycleState,
    Opportunity,
    OrderPlan,
    OrderType,
    SourceKind,
)


NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def valid_order_plan() -> OrderPlan:
    return OrderPlan(
        direction=Direction.LONG,
        order_type=OrderType.LIMIT,
        entry_low=Decimal("100"),
        entry_high=Decimal("101"),
        stop=Decimal("98"),
        targets=[Decimal("104"), Decimal("107")],
        target_allocations=[Decimal("0.5"), Decimal("0.5")],
        expires_at=NOW + timedelta(minutes=5),
        max_slippage_bps=Decimal("8"),
        suggested_quantity=Decimal("10"),
        risk_amount=Decimal("30"),
        reward_to_risk=Decimal("2"),
        invalidation="5m close below 98",
    )


def test_actionable_opportunity_requires_order_plan() -> None:
    with pytest.raises(ValidationError, match="order_plan"):
        Opportunity(
            id="btc-entry",
            symbol="BTCUSDT",
            source=SourceKind.NATIVE,
            state=LifecycleState.ENTRY_VALID,
            confidence=80,
            created_at=NOW,
            updated_at=NOW,
            evidence=[Evidence(code="trend", text="1h trend up", weight=20)],
            data_health=DataHealth(healthy=True, observed_at=NOW),
        )


def test_non_actionable_opportunity_can_omit_order_plan() -> None:
    opportunity = Opportunity(
        id="sol-forming",
        symbol="SOLUSDT",
        source=SourceKind.NATIVE,
        state=LifecycleState.FORMING,
        confidence=61,
        created_at=NOW,
        updated_at=NOW,
        evidence=[],
        data_health=DataHealth(healthy=True, observed_at=NOW),
    )
    assert opportunity.order_plan is None


def test_order_plan_rejects_stop_on_wrong_side() -> None:
    payload = valid_order_plan().model_dump()
    payload["stop"] = Decimal("102")
    with pytest.raises(ValidationError, match="stop"):
        OrderPlan.model_validate(payload)


def test_order_plan_requires_allocations_to_sum_to_one() -> None:
    payload = valid_order_plan().model_dump()
    payload["target_allocations"] = [Decimal("0.5"), Decimal("0.4")]
    with pytest.raises(ValidationError, match="allocations"):
        OrderPlan.model_validate(payload)


def test_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        DataHealth(healthy=True, observed_at=datetime(2026, 8, 1, 8, 0))

from datetime import timedelta
from decimal import Decimal

from crypto_signal_terminal.domain.models import Direction, MarketSnapshot, OrderPlan, OrderType


def basic_order_plan(
    snapshot: MarketSnapshot,
    direction: Direction,
    *,
    order_type: OrderType,
    ttl_minutes: int = 5,
    risk_amount: Decimal = Decimal("25"),
) -> OrderPlan:
    price = snapshot.price
    distance = max(price * Decimal("0.006"), Decimal("0.000001"))
    half_spread = (snapshot.ask - snapshot.bid) / Decimal("2")
    if order_type is OrderType.LIMIT:
        entry_low = price - half_spread if direction is Direction.LONG else price
        entry_high = price if direction is Direction.LONG else price + half_spread
    else:
        entry_low = snapshot.ask if direction is Direction.LONG else snapshot.bid
        entry_high = entry_low
    if direction is Direction.LONG:
        stop = entry_low - distance
        targets = (entry_high + distance * Decimal("1.5"), entry_high + distance * Decimal("3"))
    else:
        stop = entry_high + distance
        targets = (entry_low - distance * Decimal("1.5"), entry_low - distance * Decimal("3"))
    quantity = risk_amount / (abs(((entry_low + entry_high) / Decimal("2")) - stop))
    return OrderPlan(
        direction=direction,
        order_type=order_type,
        entry_low=entry_low,
        entry_high=entry_high,
        stop=stop,
        targets=targets,
        target_allocations=(Decimal("0.5"), Decimal("0.5")),
        expires_at=snapshot.observed_at + timedelta(minutes=ttl_minutes),
        max_slippage_bps=Decimal("10"),
        suggested_quantity=quantity,
        risk_amount=risk_amount,
        reward_to_risk=Decimal("2.25"),
        invalidation=("5m close below structural stop" if direction is Direction.LONG else "5m close above structural stop"),
        estimated_fees=price * quantity * Decimal("0.0006"),
    )

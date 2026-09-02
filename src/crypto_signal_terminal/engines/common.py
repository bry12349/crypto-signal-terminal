from datetime import timedelta
from decimal import Decimal

from crypto_signal_terminal.domain.models import AssetClass, Direction, MarketSnapshot, OrderPlan, OrderType


def basic_order_plan(
    snapshot: MarketSnapshot,
    direction: Direction,
    *,
    order_type: OrderType,
    ttl_minutes: int = 5,
    risk_amount: Decimal = Decimal("25"),
    fee_rate: Decimal = Decimal("0.0006"),
    max_slippage_bps: Decimal = Decimal("10"),
) -> OrderPlan:
    price = snapshot.price
    if snapshot.asset_class is AssetClass.COMMODITY:
        profile = "COMMODITY"
    elif snapshot.asset_class is AssetClass.US_EQUITY:
        profile = "US_EQUITY"
    else:
        profile = "BTC" if snapshot.symbol == "BTCUSDT" else "ETH" if snapshot.symbol == "ETHUSDT" else "ALT"
    defaults = {"BTC": Decimal("0.006"), "ETH": Decimal("0.008"), "ALT": Decimal("0.012"), "COMMODITY": Decimal("0.010"), "US_EQUITY": Decimal("0.014")}
    floors = {"BTC": Decimal("0.0035"), "ETH": Decimal("0.005"), "ALT": Decimal("0.008"), "COMMODITY": Decimal("0.004"), "US_EQUITY": Decimal("0.006")}
    ceilings = {"BTC": Decimal("0.018"), "ETH": Decimal("0.022"), "ALT": Decimal("0.035"), "COMMODITY": Decimal("0.030"), "US_EQUITY": Decimal("0.040")}
    atr_ratio = Decimal(str(snapshot.features.get("atr_ratio", "0")))
    distance_ratio = defaults[profile] if atr_ratio <= 0 else max(floors[profile], min(ceilings[profile], atr_ratio * Decimal("1.2")))
    distance = max(price * distance_ratio, Decimal("0.000001"))
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
    midpoint = (entry_low + entry_high) / Decimal("2")
    stop_distance = abs(midpoint - stop)
    round_trip_fee_rate = fee_rate * Decimal("2")
    cost_per_unit = midpoint * (round_trip_fee_rate + max_slippage_bps / Decimal("10000"))
    quantity = risk_amount / (stop_distance + cost_per_unit)
    allocations = (Decimal("0.5"), Decimal("0.5"))
    gross_reward = sum(
        (abs(target - midpoint) * allocation for target, allocation in zip(targets, allocations, strict=True)),
        Decimal("0"),
    )
    reward_to_risk = max(Decimal("0.01"), (gross_reward - cost_per_unit) / (stop_distance + cost_per_unit))
    return OrderPlan(
        direction=direction,
        order_type=order_type,
        entry_low=entry_low,
        entry_high=entry_high,
        stop=stop,
        targets=targets,
        target_allocations=allocations,
        expires_at=snapshot.observed_at + timedelta(minutes=ttl_minutes),
        max_slippage_bps=max_slippage_bps,
        suggested_quantity=quantity,
        risk_amount=risk_amount,
        reward_to_risk=reward_to_risk,
        invalidation=("5m close below structural stop" if direction is Direction.LONG else "5m close above structural stop"),
        estimated_fees=midpoint * quantity * round_trip_fee_rate,
    )

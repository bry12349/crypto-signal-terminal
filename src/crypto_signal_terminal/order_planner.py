from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from crypto_signal_terminal.domain.models import Direction, MarketSnapshot, OrderPlan, OrderType, TelegramSignal


class RiskSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_equity: Decimal = Field(default=Decimal("10000"), gt=0)
    risk_fraction: Decimal = Field(default=Decimal("0.0025"), gt=0, le=Decimal("0.02"))
    fee_rate: Decimal = Field(default=Decimal("0.0006"), ge=0)
    max_slippage_bps: Decimal = Field(default=Decimal("10"), ge=0, le=Decimal("100"))


class OrderPlanner:
    def __init__(self, settings: RiskSettings | None = None) -> None:
        self.settings = settings or RiskSettings()

    def from_telegram(self, signal: TelegramSignal, market: MarketSnapshot) -> OrderPlan:
        if signal.direction is None or signal.entry_low is None or signal.entry_high is None:
            raise ValueError("signal direction and entry are required")
        if signal.stop is None or not signal.targets:
            raise ValueError("signal stop and targets are required")
        if signal.direction is Direction.LONG:
            if signal.stop >= signal.entry_low:
                raise ValueError("long stop must be below entry")
            targets = tuple(target for target in signal.targets if target > signal.entry_high)
        else:
            if signal.stop <= signal.entry_high:
                raise ValueError("short stop must be above entry")
            targets = tuple(target for target in signal.targets if target < signal.entry_low)
        if not targets:
            raise ValueError("targets are on the wrong side of entry")
        midpoint = (signal.entry_low + signal.entry_high) / Decimal("2")
        distance = abs(midpoint - signal.stop)
        risk_amount = self.settings.account_equity * self.settings.risk_fraction
        cost_per_unit = midpoint * (self.settings.fee_rate + self.settings.max_slippage_bps / Decimal("10000"))
        quantity = risk_amount / (distance + cost_per_unit)
        weights = self._allocations(len(targets))
        average_reward = sum((abs(target - midpoint) * allocation for target, allocation in zip(targets, weights, strict=True)), Decimal("0"))
        net_risk = distance + cost_per_unit
        reward_to_risk = max(Decimal("0.01"), average_reward / net_risk)
        within_entry = signal.entry_low <= market.price <= signal.entry_high
        order_type = OrderType.LIMIT if within_entry else OrderType.STOP_MARKET
        return OrderPlan(
            direction=signal.direction,
            order_type=order_type,
            entry_low=signal.entry_low,
            entry_high=signal.entry_high,
            stop=signal.stop,
            targets=targets,
            target_allocations=weights,
            expires_at=market.observed_at + timedelta(minutes=6),
            max_slippage_bps=self.settings.max_slippage_bps,
            suggested_quantity=quantity,
            risk_amount=risk_amount,
            reward_to_risk=reward_to_risk,
            invalidation=(f"Price closes below {signal.stop}" if signal.direction is Direction.LONG else f"Price closes above {signal.stop}"),
            estimated_fees=midpoint * quantity * self.settings.fee_rate,
        )

    @staticmethod
    def _allocations(count: int) -> tuple[Decimal, ...]:
        if count == 1:
            return (Decimal("1"),)
        if count == 2:
            return (Decimal("0.5"), Decimal("0.5"))
        base = Decimal("1") / Decimal(count)
        values = [base for _ in range(count)]
        values[-1] += Decimal("1") - sum(values, Decimal("0"))
        return tuple(values)

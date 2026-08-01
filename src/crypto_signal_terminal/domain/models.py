from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"


class LifecycleState(StrEnum):
    FORMING = "FORMING"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    ENTRY_VALID = "ENTRY_VALID"
    MANAGING = "MANAGING"
    CLOSED = "CLOSED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class Verdict(StrEnum):
    CONFIRMED = "CONFIRMED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNPARSEABLE = "UNPARSEABLE"


class SourceKind(StrEnum):
    NATIVE = "NATIVE"
    TELEGRAM = "TELEGRAM"
    SMART_MONEY = "SMART_MONEY"
    DEMO = "DEMO"


class SmartMoneyKind(StrEnum):
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    DERIVATIVES_FLOW = "DERIVATIVES_FLOW"
    ONCHAIN_CLUSTER = "ONCHAIN_CLUSTER"


class DataHealth(FrozenModel):
    healthy: bool
    observed_at: datetime
    latency_ms: int = Field(default=0, ge=0)
    stale_sources: tuple[str, ...] = ()
    reason: str | None = None

    @model_validator(mode="after")
    def validate_time(self) -> DataHealth:
        if not _is_aware(self.observed_at):
            raise ValueError("observed_at must include timezone information")
        return self


class Evidence(FrozenModel):
    code: str
    text: str
    weight: int = Field(ge=-100, le=100)
    value: Decimal | None = None
    source: str | None = None


class OrderPlan(FrozenModel):
    direction: Direction
    order_type: OrderType
    entry_low: Decimal = Field(gt=0)
    entry_high: Decimal = Field(gt=0)
    stop: Decimal = Field(gt=0)
    targets: tuple[Decimal, ...] = Field(min_length=1)
    target_allocations: tuple[Decimal, ...] = Field(min_length=1)
    expires_at: datetime
    max_slippage_bps: Decimal = Field(ge=0)
    suggested_quantity: Decimal = Field(gt=0)
    risk_amount: Decimal = Field(gt=0)
    reward_to_risk: Decimal = Field(gt=0)
    invalidation: str = Field(min_length=3)
    estimated_fees: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def validate_plan(self) -> OrderPlan:
        if not _is_aware(self.expires_at):
            raise ValueError("expires_at must include timezone information")
        if self.entry_low > self.entry_high:
            raise ValueError("entry_low must not exceed entry_high")
        if len(self.targets) != len(self.target_allocations):
            raise ValueError("targets and allocations must have equal length")
        if abs(sum(self.target_allocations, Decimal("0")) - Decimal("1")) > Decimal("0.0001"):
            raise ValueError("target allocations must sum to one")
        if any(allocation <= 0 for allocation in self.target_allocations):
            raise ValueError("target allocations must be positive")
        if self.direction is Direction.LONG:
            if self.stop >= self.entry_low:
                raise ValueError("long stop must be below entry")
            if any(target <= self.entry_high for target in self.targets):
                raise ValueError("long targets must be above entry")
        else:
            if self.stop <= self.entry_high:
                raise ValueError("short stop must be above entry")
            if any(target >= self.entry_low for target in self.targets):
                raise ValueError("short targets must be below entry")
        return self


class Opportunity(FrozenModel):
    id: str
    symbol: str = Field(pattern=r"^[A-Z0-9]{2,20}$")
    source: SourceKind
    state: LifecycleState
    confidence: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    evidence: tuple[Evidence, ...]
    data_health: DataHealth
    order_plan: OrderPlan | None = None
    title: str | None = None
    risk: str | None = None
    source_label: str | None = None

    @model_validator(mode="after")
    def validate_opportunity(self) -> Opportunity:
        if not _is_aware(self.created_at) or not _is_aware(self.updated_at):
            raise ValueError("opportunity timestamps must include timezone information")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        actionable = {LifecycleState.TRIGGERED, LifecycleState.ENTRY_VALID, LifecycleState.MANAGING}
        if self.state in actionable and self.order_plan is None:
            raise ValueError("actionable opportunity requires order_plan")
        return self


class TelegramSignal(FrozenModel):
    account_id: str
    channel_id: int
    message_id: int
    published_at: datetime
    edited_at: datetime | None = None
    raw_text: str
    symbol: str | None = None
    direction: Direction | None = None
    entry_low: Decimal | None = None
    entry_high: Decimal | None = None
    stop: Decimal | None = None
    targets: tuple[Decimal, ...] = ()
    leverage: Decimal | None = None
    parse_confidence: int = Field(default=0, ge=0, le=100)
    issues: tuple[str, ...] = ()


class SmartMoneyCandidate(FrozenModel):
    id: str
    symbol: str
    kind: SmartMoneyKind
    direction: Direction
    score: int = Field(ge=0, le=100)
    observed_at: datetime
    evidence: tuple[Evidence, ...]
    wallet: str | None = None
    chain: str | None = None


class ConfirmationResult(FrozenModel):
    id: str
    signal: TelegramSignal
    verdict: Verdict
    confidence: int = Field(ge=0, le=100)
    analyzed_at: datetime
    evidence: tuple[Evidence, ...] = ()
    reason_codes: tuple[str, ...] = ()
    order_plan: OrderPlan | None = None
    community_plan: OrderPlan | None = None


class Candle(FrozenModel):
    timestamp: int = Field(gt=0)
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)


class MarketSnapshot(FrozenModel):
    symbol: str
    exchange: str
    observed_at: datetime
    price: Decimal = Field(gt=0)
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    open_interest: Decimal = Field(ge=0)
    funding_rate: Decimal = Decimal("0")
    volume_24h: Decimal = Field(default=Decimal("0"), ge=0)
    features: dict[str, Decimal | int | bool | str] = Field(default_factory=dict)
    data_health: DataHealth
    peer_confirmations: int = Field(default=1, ge=0)
    candles: tuple[Candle, ...] = ()


JsonValue = Annotated[dict[str, Any], Field(default_factory=dict)]

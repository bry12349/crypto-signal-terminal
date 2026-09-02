from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class AssetClass(StrEnum):
    """Market family; each family is evaluated by an isolated model."""

    CRYPTO = "CRYPTO"
    COMMODITY = "COMMODITY"
    US_EQUITY = "US_EQUITY"


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


class SourceKind(StrEnum):
    NATIVE = "NATIVE"
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


class CalibrationState(FrozenModel):
    settled: int = Field(ge=0)
    mean_predicted: Decimal = Field(ge=0, le=1)
    observed_win_rate: Decimal = Field(ge=0, le=1)
    absolute_error: Decimal = Field(ge=0, le=1)
    brier_score: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    status: Literal["INSUFFICIENT", "VALIDATED", "DEGRADED"]


class NarrativeObservation(FrozenModel):
    """A public, attributable market opinion; never an execution instruction."""

    id: str
    source_id: str
    source_name: str
    source_kind: Literal["FORUM", "ANALYST", "COPY_TRADER", "NEWS"]
    published_at: datetime
    symbols: tuple[str, ...] = Field(min_length=1)
    stance: Decimal = Field(ge=-1, le=1)
    confidence: Decimal = Field(ge=0, le=1)
    source_prior: Decimal = Field(ge=0, le=1)
    text: str
    url: str | None = None
    historical_hit_rate: Decimal | None = Field(default=None, ge=0, le=1)
    settled_calls: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_published_at(self) -> NarrativeObservation:
        if not _is_aware(self.published_at):
            raise ValueError("published_at must include timezone information")
        return self


class NarrativeAssessment(FrozenModel):
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL", "UNCONFIRMED", "UNAVAILABLE"]
    score: Decimal = Field(ge=-1, le=1)
    confidence: Decimal = Field(ge=0, le=1)
    independent_sources: int = Field(ge=0)
    sources: tuple[str, ...] = ()


class SignalAnalysis(FrozenModel):
    opportunity_score: int = Field(ge=0, le=100)
    confidence: int = Field(ge=0, le=100)
    p_tp_before_sl: Decimal = Field(ge=0, le=1)
    expected_value: Decimal
    evidence_conflict: Decimal = Field(ge=0, le=1)
    is_tradeable: bool
    market_regime: str
    signal_type: str
    smart_money_bias: str
    derivatives_bias: str
    order_flow_bias: str
    news_bias: str
    asset_profile: str = "UNKNOWN"
    model_version: str = "0.7.0"
    narrative_bias: str = "UNAVAILABLE"
    narrative_score: Decimal = Field(default=Decimal("0"), ge=-1, le=1)
    narrative_sources: tuple[str, ...] = ()
    calibration: CalibrationState
    decision: SignalDecision


class DecisionGate(FrozenModel):
    key: str
    label: str
    passed: bool
    observed: Decimal
    required: Decimal


class SignalDecision(FrozenModel):
    outcome: Literal["TRADE", "NO_TRADE"]
    gates: tuple[DecisionGate, ...]


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
    analysis: SignalAnalysis | None = None

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
    token_address: str | None = None
    display_symbol: str | None = None


class Candle(FrozenModel):
    timestamp: int = Field(gt=0)
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)


class MarketSnapshot(FrozenModel):
    symbol: str
    asset_class: AssetClass = AssetClass.CRYPTO
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

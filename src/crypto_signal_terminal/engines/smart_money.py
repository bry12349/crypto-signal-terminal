from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from crypto_signal_terminal.domain.models import (
    Direction,
    Evidence,
    FrozenModel,
    MarketSnapshot,
    SmartMoneyCandidate,
    SmartMoneyKind,
)


class WalletObservation(FrozenModel):
    wallet: str
    chain: str
    timestamp: datetime
    realized_return: Decimal
    max_drawdown: Decimal = Field(ge=0)
    token: str
    side: str | None = None
    value_usd: Decimal = Decimal("0")
    tx_hash: str | None = None


class WalletScore(FrozenModel):
    wallet: str
    score: int = Field(ge=0, le=100)
    observation_count: int = Field(ge=0)
    hit_rate: Decimal
    median_return: Decimal
    max_drawdown: Decimal


def score_wallet(history: list[WalletObservation], *, as_of: datetime) -> WalletScore:
    eligible = [item for item in history if item.timestamp <= as_of]
    if not eligible:
        return WalletScore(wallet="unknown", score=0, observation_count=0, hit_rate=Decimal("0"), median_return=Decimal("0"), max_drawdown=Decimal("0"))
    returns = sorted(item.realized_return for item in eligible)
    midpoint = len(returns) // 2
    median = returns[midpoint] if len(returns) % 2 else (returns[midpoint - 1] + returns[midpoint]) / Decimal("2")
    hits = sum(1 for item in eligible if item.realized_return > 0)
    hit_rate = Decimal(hits) / Decimal(len(eligible))
    drawdown = max((item.max_drawdown for item in eligible), default=Decimal("0"))
    sample_factor = min(Decimal("1"), Decimal(len(eligible)) / Decimal("8"))
    raw = Decimal("35") + hit_rate * Decimal("25") + max(Decimal("0"), median) * Decimal("25") + sample_factor * Decimal("20") - drawdown * Decimal("20")
    score = max(0, min(100, int(raw)))
    return WalletScore(wallet=eligible[0].wallet, score=score, observation_count=len(eligible), hit_rate=hit_rate, median_return=median, max_drawdown=drawdown)


def _d(snapshot: MarketSnapshot, key: str, default: str = "0") -> Decimal:
    return Decimal(str(snapshot.features.get(key, default)))


class SmartMoneyEngine:
    def evaluate_flow(self, snapshot: MarketSnapshot) -> SmartMoneyCandidate | None:
        if not snapshot.data_health.healthy:
            return None
        count = int(snapshot.features.get("large_trade_count", 0))
        persistence = _d(snapshot, "flow_persistence")
        flow = _d(snapshot, "aggressive_flow_imbalance")
        oi = _d(snapshot, "oi_change_ratio")
        impact = _d(snapshot, "price_impact_bps")
        absorption = _d(snapshot, "absorption")
        if count < 3 or persistence < Decimal("0.55") or abs(flow) < Decimal("0.35") or oi < Decimal("0.02"):
            return None
        direction = Direction.LONG if flow > 0 else Direction.SHORT
        evidence = (
            Evidence(code="persistent_large_flow", text="大额主动订单流跨窗口持续", weight=30, value=persistence),
            Evidence(code="oi_participation", text="持仓量确认有新增仓位介入", weight=25, value=oi),
            Evidence(code="impact_or_absorption", text="大额流量形成价格冲击或被持续吸收", weight=20, value=max(abs(impact), abs(absorption))),
        )
        score = min(95, 55 + count * 2 + int(persistence * 20) + int(abs(flow) * 10))
        return SmartMoneyCandidate(
            id=f"smart-flow:{snapshot.symbol}:{int(snapshot.observed_at.timestamp())}",
            symbol=snapshot.symbol,
            kind=SmartMoneyKind.DERIVATIVES_FLOW,
            direction=direction,
            score=score,
            observed_at=snapshot.observed_at,
            evidence=evidence,
        )

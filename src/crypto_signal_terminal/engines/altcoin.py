from __future__ import annotations

from decimal import Decimal

from crypto_signal_terminal.domain.models import (
    Direction,
    Evidence,
    LifecycleState,
    MarketSnapshot,
    Opportunity,
    OrderType,
    SourceKind,
)
from crypto_signal_terminal.engines.common import basic_order_plan
from crypto_signal_terminal.engines.evidence_fusion import EvidenceFusion


def _d(snapshot: MarketSnapshot, key: str, default: str = "0") -> Decimal:
    return Decimal(str(snapshot.features.get(key, default)))


class AltcoinEngine:
    def __init__(self, *, max_spread_bps: Decimal = Decimal("25")) -> None:
        self.max_spread_bps = max_spread_bps
        self.fusion = EvidenceFusion()

    def evaluate(self, snapshot: MarketSnapshot) -> Opportunity | None:
        if not snapshot.data_health.healthy or snapshot.symbol in {"BTCUSDT", "ETHUSDT"}:
            return None
        spread = _d(snapshot, "spread_bps", str((snapshot.ask - snapshot.bid) / snapshot.price * Decimal("10000")))
        if spread > self.max_spread_bps or snapshot.volume_24h < Decimal("1000000"):
            return None
        atr = _d(snapshot, "atr_percentile", "50")
        volume = _d(snapshot, "volume_acceleration", "1")
        oi = _d(snapshot, "oi_change_ratio")
        flow = _d(snapshot, "aggressive_flow_imbalance")
        depth = _d(snapshot, "depth_imbalance")
        slippage = _d(snapshot, "slippage_bps_1000")
        if atr > Decimal("25") or volume < Decimal("1.5") or abs(oi) < Decimal("0.03"):
            return None
        direction = Direction.LONG if flow + depth >= 0 else Direction.SHORT
        trigger = int(snapshot.features.get("trigger_5m", 0))
        trigger_matches = trigger == (1 if direction is Direction.LONG else -1)
        cross_exchange = snapshot.peer_confirmations >= 2
        evidence = (
            Evidence(code="compression", text="波动压缩接近释放临界点", weight=24, value=atr),
            Evidence(code="oi_acceleration", text="持仓量在扩张前明显加速", weight=24, value=oi),
            Evidence(code="microstructure", text="主动成交与盘口失衡方向一致", weight=22, value=flow + depth),
        )
        liquid_enough = slippage <= Decimal("15")
        candidate_plan = basic_order_plan(snapshot, direction, order_type=OrderType.MARKET, ttl_minutes=3)
        analysis = self.fusion.evaluate(
            snapshot,
            direction=direction,
            reward_to_risk=candidate_plan.reward_to_risk,
            signal_type="volatility_expansion",
        )
        evidence = evidence + (
            Evidence(code="tp_before_sl", text="模型估计 TP 先于 SL 的概率", weight=16, value=analysis.p_tp_before_sl),
            Evidence(code="expected_value", text="计入费用与滑点后的净期望值", weight=16, value=analysis.expected_value),
        )
        state = LifecycleState.ENTRY_VALID if trigger_matches and cross_exchange and liquid_enough and analysis.is_tradeable else LifecycleState.ARMED
        plan = candidate_plan if state is LifecycleState.ENTRY_VALID else None
        return Opportunity(
            id=f"alt:{snapshot.symbol}:{state.value.lower()}",
            symbol=snapshot.symbol,
            source=SourceKind.NATIVE,
            state=state,
            confidence=analysis.confidence,
            created_at=snapshot.observed_at,
            updated_at=snapshot.observed_at,
            evidence=evidence,
            data_health=snapshot.data_health,
            order_plan=plan,
            title="临界起爆" if direction is Direction.LONG else "临界瀑布",
            risk=None if state is LifecycleState.ENTRY_VALID else "等待触发、跨交易所确认、流动性或净期望值门槛恢复",
            analysis=analysis,
        )

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from crypto_signal_terminal.domain.models import AssetClass, CalibrationState, Direction, Evidence, LifecycleState, MarketSnapshot, Opportunity, OrderType, SourceKind
from crypto_signal_terminal.engines.common import basic_order_plan
from crypto_signal_terminal.engines.evidence_fusion import EvidenceFusion


def _d(snapshot: MarketSnapshot, key: str, default: str = "0") -> Decimal:
    try:
        return Decimal(str(snapshot.features.get(key, default)))
    except Exception:
        return Decimal(default)


class CommodityEngine:
    """Macro/term-structure model for metals, energy and soft commodities."""

    def __init__(self, *, max_spread_bps: Decimal = Decimal("8")) -> None:
        self.max_spread_bps = max_spread_bps
        self.fusion = EvidenceFusion()

    def evaluate(self, snapshot: MarketSnapshot, *, calibration: CalibrationState | None = None, calibration_for_direction: Callable[[Direction], CalibrationState] | None = None) -> Opportunity | None:
        if snapshot.asset_class is not AssetClass.COMMODITY or not snapshot.data_health.healthy:
            return None
        spread = _d(snapshot, "spread_bps", str((snapshot.ask - snapshot.bid) / snapshot.price * Decimal("10000")))
        slippage = _d(snapshot, "slippage_bps_1000", "9999")
        liquidity = _d(snapshot, "session_liquidity", "0")
        event_risk = _d(snapshot, "event_risk", "1")
        if spread > self.max_spread_bps or slippage > self.max_spread_bps or liquidity < Decimal("0.55") or event_risk > Decimal("0.45"):
            return None
        trend = _d(snapshot, "trend_1d") * Decimal("0.35") + _d(snapshot, "trend_4h") * Decimal("0.35") + _d(snapshot, "trend_1h") * Decimal("0.20") + _d(snapshot, "trigger_5m") * Decimal("0.10")
        macro = _d(snapshot, "macro_score")
        term = _d(snapshot, "term_structure_score")
        flow = _d(snapshot, "commodity_flow", str(_d(snapshot, "aggressive_flow_imbalance")))
        score = trend * Decimal("0.48") + macro * Decimal("0.28") + term * Decimal("0.14") + flow * Decimal("0.10")
        if abs(score) < Decimal("0.22"):
            return None
        direction = Direction.LONG if score > 0 else Direction.SHORT
        if calibration_for_direction is not None:
            calibration = calibration_for_direction(direction)
        plan = basic_order_plan(snapshot, direction, order_type=OrderType.MARKET, ttl_minutes=15)
        analysis = self.fusion.evaluate(snapshot, direction=direction, reward_to_risk=plan.reward_to_risk, signal_type="commodity_macro", calibration=calibration, profile_override="COMMODITY")
        evidence = (
            Evidence(code="commodity_trend", text="日线、4小时与1小时商品趋势结构", weight=28, value=trend),
            Evidence(code="macro_driver", text="宏观驱动与商品方向一致", weight=24, value=macro),
            Evidence(code="term_structure", text="期限结构/现货基差确认", weight=14, value=term),
            Evidence(code="commodity_flow", text="商品合约主动成交流向", weight=10, value=flow),
            Evidence(code="asset_model", text="COMMODITY 独立宏观模型 · v0.8.0-commodity", weight=0),
            Evidence(code="event_gate", text="库存、央行与宏观数据事件风险已过滤", weight=8, value=event_risk),
            Evidence(code="tp_before_sl", text="模型估计 TP 先于 SL 的概率", weight=16, value=analysis.p_tp_before_sl),
        )
        trigger = int(_d(snapshot, "trigger_5m")) == (1 if direction is Direction.LONG else -1)
        state = LifecycleState.ENTRY_VALID if trigger and analysis.is_tradeable else LifecycleState.ARMED
        return Opportunity(id=f"commodity:{snapshot.symbol}:{state.value.lower()}", symbol=snapshot.symbol, source=SourceKind.NATIVE, state=state, confidence=analysis.confidence, created_at=snapshot.observed_at, updated_at=snapshot.observed_at, evidence=evidence, data_health=snapshot.data_health, order_plan=plan if state is LifecycleState.ENTRY_VALID else None, title="商品宏观趋势做多" if direction is Direction.LONG else "商品宏观趋势做空", risk=None if state is LifecycleState.ENTRY_VALID else "等待触发或商品模型门槛恢复", analysis=analysis)

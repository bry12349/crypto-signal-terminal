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


class EquityEngine:
    """US equity-contract model: index regime, relative strength and gap risk."""

    def __init__(self, *, max_spread_bps: Decimal = Decimal("5")) -> None:
        self.max_spread_bps = max_spread_bps
        self.fusion = EvidenceFusion()

    def evaluate(self, snapshot: MarketSnapshot, *, calibration: CalibrationState | None = None, calibration_for_direction: Callable[[Direction], CalibrationState] | None = None) -> Opportunity | None:
        if snapshot.asset_class is not AssetClass.US_EQUITY or not snapshot.data_health.healthy:
            return None
        spread = _d(snapshot, "spread_bps", str((snapshot.ask - snapshot.bid) / snapshot.price * Decimal("10000")))
        slippage = _d(snapshot, "slippage_bps_1000", "9999")
        session = _d(snapshot, "session_liquidity", "0")
        earnings = _d(snapshot, "earnings_risk", "1")
        gap = _d(snapshot, "gap_risk", "1")
        if spread > self.max_spread_bps or slippage > Decimal("6") or session < Decimal("0.55") or earnings > Decimal("0.45") or gap > Decimal("0.60"):
            return None
        trend = _d(snapshot, "trend_4h") * Decimal("0.40") + _d(snapshot, "trend_1h") * Decimal("0.30") + _d(snapshot, "trigger_5m") * Decimal("0.12") + _d(snapshot, "relative_strength") * Decimal("0.18")
        index = _d(snapshot, "index_regime")
        relative = _d(snapshot, "relative_strength")
        flow = _d(snapshot, "equity_flow", str(_d(snapshot, "aggressive_flow_imbalance")))
        score = trend * Decimal("0.45") + index * Decimal("0.25") + relative * Decimal("0.20") + flow * Decimal("0.10")
        if abs(score) < Decimal("0.24") or score * index < Decimal("-0.10"):
            return None
        direction = Direction.LONG if score > 0 else Direction.SHORT
        if calibration_for_direction is not None:
            calibration = calibration_for_direction(direction)
        plan = basic_order_plan(snapshot, direction, order_type=OrderType.MARKET, ttl_minutes=10)
        analysis = self.fusion.evaluate(snapshot, direction=direction, reward_to_risk=plan.reward_to_risk, signal_type="equity_relative_strength", calibration=calibration, profile_override="US_EQUITY")
        evidence = (
            Evidence(code="equity_trend", text="股票自身多周期趋势结构", weight=24, value=trend),
            Evidence(code="index_regime", text="SPX/NQ 市场风险偏好确认", weight=22, value=index),
            Evidence(code="relative_strength", text="相对基准强弱领先", weight=20, value=relative),
            Evidence(code="equity_flow", text="股票合约主动成交与成交量确认", weight=12, value=flow),
            Evidence(code="asset_model", text="US_EQUITY 独立相对强弱模型 · v0.8.0-us-equity", weight=0),
            Evidence(code="risk_gate", text="财报与开盘跳空风险已过滤", weight=8, value=max(earnings, gap)),
            Evidence(code="tp_before_sl", text="模型估计 TP 先于 SL 的概率", weight=16, value=analysis.p_tp_before_sl),
        )
        trigger = int(_d(snapshot, "trigger_5m")) == (1 if direction is Direction.LONG else -1)
        state = LifecycleState.ENTRY_VALID if trigger and analysis.is_tradeable else LifecycleState.ARMED
        return Opportunity(id=f"equity:{snapshot.symbol}:{state.value.lower()}", symbol=snapshot.symbol, source=SourceKind.NATIVE, state=state, confidence=analysis.confidence, created_at=snapshot.observed_at, updated_at=snapshot.observed_at, evidence=evidence, data_health=snapshot.data_health, order_plan=plan if state is LifecycleState.ENTRY_VALID else None, title="美股相对强弱做多" if direction is Direction.LONG else "美股相对强弱做空", risk=None if state is LifecycleState.ENTRY_VALID else "等待触发或股票模型门槛恢复", analysis=analysis)

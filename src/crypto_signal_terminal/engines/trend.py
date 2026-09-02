from __future__ import annotations

from decimal import Decimal
from typing import Callable

from crypto_signal_terminal.domain.models import (
    CalibrationState,
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


def _decimal(snapshot: MarketSnapshot, key: str, default: str = "0") -> Decimal:
    return Decimal(str(snapshot.features.get(key, default)))


class TrendEngine:
    def __init__(self) -> None:
        self.fusion = EvidenceFusion()

    def evaluate(self, snapshot: MarketSnapshot, *, calibration: CalibrationState | None = None, calibration_for_direction: Callable[[Direction], CalibrationState] | None = None) -> Opportunity | None:
        if not snapshot.data_health.healthy or snapshot.symbol not in {"BTCUSDT", "ETHUSDT"}:
            return None
        trend_4h = int(snapshot.features.get("trend_4h", 0))
        trend_1h = int(snapshot.features.get("trend_1h", 0))
        setup_15m = int(snapshot.features.get("setup_15m", 0))
        trigger_5m = int(snapshot.features.get("trigger_5m", 0))
        if trend_4h == 0 or trend_4h != trend_1h or setup_15m != trend_4h:
            return None
        direction = Direction.LONG if trend_4h > 0 else Direction.SHORT
        if calibration_for_direction is not None:
            calibration = calibration_for_direction(direction)
        matching_trigger = trigger_5m == trend_4h
        directional_flow = _decimal(snapshot, "aggressive_flow_imbalance") * Decimal(trend_4h)
        flow_confirmed = directional_flow >= Decimal("0.10")
        slippage = _decimal(snapshot, "slippage_bps_1000")
        liquid_enough = slippage <= Decimal("15")
        if slippage > Decimal("50"):
            return None
        evidence = (
            Evidence(code="multi_timeframe", text="4h 与 1h 趋势同向", weight=28),
            Evidence(code="setup", text="15m 顺势结构成立", weight=22),
            Evidence(
                code="flow" if flow_confirmed else "flow_pending",
                text="主动订单流支持趋势" if flow_confirmed else "主动订单流尚未确认该方向",
                weight=18 if flow_confirmed else -12,
                value=_decimal(snapshot, "aggressive_flow_imbalance"),
            ),
        )
        order_type = OrderType.MARKET if abs(_decimal(snapshot, "aggressive_flow_imbalance")) >= Decimal("0.45") else OrderType.LIMIT
        candidate_plan = basic_order_plan(snapshot, direction, order_type=order_type, ttl_minutes=5)
        analysis = self.fusion.evaluate(
            snapshot,
            direction=direction,
            reward_to_risk=candidate_plan.reward_to_risk,
            signal_type="trend_continuation",
            calibration=calibration,
        )
        evidence = evidence + (
            Evidence(code="asset_model", text=f"{analysis.asset_profile} 专用权重模型 · v{analysis.model_version}", weight=0),
            Evidence(code="tp_before_sl", text="模型估计 TP 先于 SL 的概率", weight=16, value=analysis.p_tp_before_sl),
            Evidence(code="expected_value", text="计入费用与滑点后的净期望值", weight=16, value=analysis.expected_value),
        )
        if analysis.narrative_sources:
            evidence += (Evidence(
                code="public_narrative", text=f"{len(analysis.narrative_sources)} 个独立公开来源共识：{analysis.narrative_bias}",
                weight=4 if snapshot.symbol == "BTCUSDT" else 4, value=analysis.narrative_score,
                source=" | ".join(analysis.narrative_sources),
            ),)
        if snapshot.symbol == "BTCUSDT" and snapshot.features.get("btc_cycle_phase"):
            evidence += (Evidence(
                code="btc_block_cycle", text=f"区块高度周期背景：{snapshot.features['btc_cycle_phase']}",
                weight=8, value=_decimal(snapshot, "btc_cycle_bias"), source="public_bitcoin_tip_height",
            ),)
        if not matching_trigger or not flow_confirmed or not liquid_enough or not analysis.is_tradeable:
            return Opportunity(
                id=f"trend:{snapshot.symbol}:armed",
                symbol=snapshot.symbol,
                source=SourceKind.NATIVE,
                state=LifecycleState.ARMED,
                confidence=analysis.confidence,
                created_at=snapshot.observed_at,
                updated_at=snapshot.observed_at,
                evidence=evidence,
                data_health=snapshot.data_health,
                title="等待顺势回调触发",
                risk="5m 触发、订单流、流动性或净期望值门槛尚未通过",
                analysis=analysis,
            )
        return Opportunity(
            id=f"trend:{snapshot.symbol}:entry",
            symbol=snapshot.symbol,
            source=SourceKind.NATIVE,
            state=LifecycleState.ENTRY_VALID,
            confidence=analysis.confidence,
            created_at=snapshot.observed_at,
            updated_at=snapshot.observed_at,
            evidence=evidence,
            data_health=snapshot.data_health,
            order_plan=candidate_plan,
            title="日内趋势跟随",
            risk="触及结构止损则趋势判断失效",
            analysis=analysis,
        )

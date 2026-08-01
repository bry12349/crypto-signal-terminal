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


def _decimal(snapshot: MarketSnapshot, key: str, default: str = "0") -> Decimal:
    return Decimal(str(snapshot.features.get(key, default)))


class TrendEngine:
    def evaluate(self, snapshot: MarketSnapshot) -> Opportunity | None:
        if not snapshot.data_health.healthy or snapshot.symbol not in {"BTCUSDT", "ETHUSDT"}:
            return None
        trend_4h = int(snapshot.features.get("trend_4h", 0))
        trend_1h = int(snapshot.features.get("trend_1h", 0))
        setup_15m = int(snapshot.features.get("setup_15m", 0))
        trigger_5m = int(snapshot.features.get("trigger_5m", 0))
        if trend_4h == 0 or trend_4h != trend_1h or setup_15m == 0:
            return None
        direction = Direction.LONG if trend_4h > 0 else Direction.SHORT
        matching_trigger = trigger_5m == trend_4h
        evidence = (
            Evidence(code="multi_timeframe", text="4h 与 1h 趋势同向", weight=28),
            Evidence(code="setup", text="15m 顺势回调结构成立", weight=22),
            Evidence(code="flow", text="主动订单流支持趋势", weight=18, value=_decimal(snapshot, "aggressive_flow_imbalance")),
        )
        if not matching_trigger:
            return Opportunity(
                id=f"trend:{snapshot.symbol}:{int(snapshot.observed_at.timestamp())}:armed",
                symbol=snapshot.symbol,
                source=SourceKind.NATIVE,
                state=LifecycleState.ARMED,
                confidence=66,
                created_at=snapshot.observed_at,
                updated_at=snapshot.observed_at,
                evidence=evidence,
                data_health=snapshot.data_health,
                title="等待顺势回调触发",
                risk="5m 触发尚未确认",
            )
        flow = abs(_decimal(snapshot, "aggressive_flow_imbalance"))
        order_type = OrderType.MARKET if flow >= Decimal("0.45") else OrderType.LIMIT
        plan = basic_order_plan(snapshot, direction, order_type=order_type, ttl_minutes=5)
        return Opportunity(
            id=f"trend:{snapshot.symbol}:{int(snapshot.observed_at.timestamp())}:entry",
            symbol=snapshot.symbol,
            source=SourceKind.NATIVE,
            state=LifecycleState.ENTRY_VALID,
            confidence=min(92, 72 + int(flow * 20)),
            created_at=snapshot.observed_at,
            updated_at=snapshot.observed_at,
            evidence=evidence,
            data_health=snapshot.data_health,
            order_plan=plan,
            title="日内趋势跟随",
            risk="触及结构止损则趋势判断失效",
        )

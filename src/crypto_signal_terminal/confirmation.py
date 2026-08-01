from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from crypto_signal_terminal.domain.models import (
    ConfirmationResult,
    Direction,
    Evidence,
    MarketSnapshot,
    TelegramSignal,
    Verdict,
)
from crypto_signal_terminal.order_planner import OrderPlanner


class ConfirmationEngine:
    def __init__(self, planner: OrderPlanner | None = None) -> None:
        self.planner = planner or OrderPlanner()

    def confirm(self, signal: TelegramSignal, market: MarketSnapshot, *, analyzed_at: datetime) -> ConfirmationResult:
        result_id = f"telegram:{signal.channel_id}:{signal.message_id}:{int(analyzed_at.timestamp())}"
        if signal.symbol is None or signal.direction is None or signal.entry_low is None or signal.entry_high is None:
            return self._result(result_id, signal, Verdict.UNPARSEABLE, analyzed_at, 0, ("essential_fields_missing",))
        if signal.symbol != market.symbol:
            return self._result(result_id, signal, Verdict.REJECTED, analyzed_at, 0, ("symbol_mismatch",))
        if not market.data_health.healthy:
            return self._result(result_id, signal, Verdict.REJECTED, analyzed_at, 0, ("stale_market",))
        if analyzed_at - signal.published_at > timedelta(minutes=15):
            return self._result(result_id, signal, Verdict.EXPIRED, analyzed_at, 10, ("message_too_old",))
        if self._entry_missed(signal, market):
            return self._result(result_id, signal, Verdict.EXPIRED, analyzed_at, 15, ("entry_missed",))

        flow = Decimal(str(market.features.get("aggressive_flow_imbalance", "0")))
        oi = Decimal(str(market.features.get("oi_change_ratio", "0")))
        trend = int(market.features.get("trend_1h", 0))
        direction_sign = 1 if signal.direction is Direction.LONG else -1
        evidence: list[Evidence] = []
        score = 48
        if trend == direction_sign:
            score += 18
            evidence.append(Evidence(code="trend_aligned", text="1h 趋势与社区方向一致", weight=18))
        if flow * direction_sign >= Decimal("0.35"):
            score += 16
            evidence.append(Evidence(code="flow_aligned", text="主动订单流确认该方向", weight=16, value=flow))
        if oi >= Decimal("0.02"):
            score += 10
            evidence.append(Evidence(code="oi_confirms", text="持仓量确认有新增仓位", weight=10, value=oi))
        if market.peer_confirmations >= 2:
            score += 8
            evidence.append(Evidence(code="cross_exchange", text="多个交易所价格相互确认", weight=8))

        try:
            plan = self.planner.from_telegram(signal, market)
        except ValueError as exc:
            return self._result(result_id, signal, Verdict.REJECTED, analyzed_at, min(score, 55), ("invalid_order_geometry", str(exc)))
        if plan.reward_to_risk < Decimal("1.2"):
            return self._result(result_id, signal, Verdict.REJECTED, analyzed_at, min(score, 55), ("poor_reward_to_risk",))
        verdict = Verdict.CONFIRMED if score >= 75 else Verdict.CONDITIONAL
        return ConfirmationResult(
            id=result_id,
            signal=signal,
            verdict=verdict,
            confidence=min(95, score),
            analyzed_at=analyzed_at,
            evidence=tuple(evidence),
            reason_codes=(),
            order_plan=plan,
            community_plan=plan,
        )

    @staticmethod
    def _entry_missed(signal: TelegramSignal, market: MarketSnapshot) -> bool:
        assert signal.direction is not None and signal.entry_low is not None and signal.entry_high is not None
        width = max(signal.entry_high - signal.entry_low, signal.entry_high * Decimal("0.002"))
        if signal.direction is Direction.LONG:
            return market.price > signal.entry_high + width * Decimal("3")
        return market.price < signal.entry_low - width * Decimal("3")

    @staticmethod
    def _result(
        result_id: str,
        signal: TelegramSignal,
        verdict: Verdict,
        analyzed_at: datetime,
        confidence: int,
        reasons: tuple[str, ...],
    ) -> ConfirmationResult:
        return ConfirmationResult(
            id=result_id,
            signal=signal,
            verdict=verdict,
            confidence=confidence,
            analyzed_at=analyzed_at,
            reason_codes=reasons,
        )

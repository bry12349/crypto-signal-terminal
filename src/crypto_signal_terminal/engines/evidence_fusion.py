from __future__ import annotations

from decimal import Decimal

from crypto_signal_terminal.domain.models import CalibrationState, DecisionGate, Direction, MarketSnapshot, SignalAnalysis, SignalDecision


ZERO = Decimal("0")
ONE = Decimal("1")


def _d(snapshot: MarketSnapshot, key: str, default: str = "0") -> Decimal:
    return Decimal(str(snapshot.features.get(key, default)))


def _clip(value: Decimal) -> Decimal:
    return max(ZERO, min(ONE, value))


def _bias(value: Decimal, *, threshold: Decimal = Decimal("0.12")) -> str:
    if value >= threshold:
        return "BULLISH"
    if value <= -threshold:
        return "BEARISH"
    return "NEUTRAL"


def _smart_money_bias(snapshot: MarketSnapshot) -> str:
    """Never relabel ordinary order flow as a smart-money observation."""
    if snapshot.features.get("smart_money_source") != "public_onchain_wallet":
        return "UNAVAILABLE"
    return _bias(_d(snapshot, "onchain_smart_money_flow"))


class EvidenceFusion:
    """Dynamic, explainable evidence fusion for a TP-before-SL estimate.

    Scores are conservative model estimates, not calibrated win-rate claims.
    Missing sources, such as news or on-chain wallet history, remain explicit.
    """

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        *,
        direction: Direction,
        reward_to_risk: Decimal,
        signal_type: str,
        calibration: CalibrationState | None = None,
    ) -> SignalAnalysis:
        trend = self._trend(snapshot)
        flow = self._flow(snapshot)
        derivatives = self._derivatives(snapshot, trend)
        anomaly = self._anomaly(snapshot, trend)
        cross_exchange = _clip(Decimal(snapshot.peer_confirmations - 1) / Decimal("2"))
        regime = self._regime(snapshot, trend, anomaly)
        weights = self._weights(regime)

        bull = self._side_score(Decimal("1"), trend, flow, derivatives, anomaly, cross_exchange, weights)
        bear = self._side_score(Decimal("-1"), trend, flow, derivatives, anomaly, cross_exchange, weights)
        lead = bull if direction is Direction.LONG else bear
        opposing = bear if direction is Direction.LONG else bull
        total = lead + opposing
        conflict = min(lead, opposing) / max(lead, opposing, Decimal("0.0001"))
        confidence = int((lead / total * Decimal("100")) if total else ZERO)
        opportunity_score = int(min(Decimal("100"), lead * Decimal("100")))
        alignment = lead / total if total else ZERO
        probability = _clip(Decimal("0.32") + alignment * Decimal("0.52") - conflict * Decimal("0.18"))
        expected_value = (probability * reward_to_risk) - (ONE - probability) - Decimal("0.08")
        calibration = calibration or CalibrationState(
            settled=0,
            mean_predicted=ZERO,
            observed_win_rate=ZERO,
            absolute_error=ZERO,
            status="INSUFFICIENT",
        )
        calibration_label = {
            "INSUFFICIENT": "历史校准：样本不足（不宣称胜率）",
            "VALIDATED": "历史校准：已通过",
            "DEGRADED": "历史校准：偏差超限",
        }[calibration.status]
        gates = (
            DecisionGate(key="tp_before_sl", label="TP 先于 SL 概率", passed=probability >= Decimal("0.56"), observed=probability, required=Decimal("0.56")),
            DecisionGate(key="expected_value", label="净期望值", passed=expected_value > ZERO, observed=expected_value, required=ZERO),
            DecisionGate(key="reward_to_risk", label="盈亏比", passed=reward_to_risk >= Decimal("1.35"), observed=reward_to_risk, required=Decimal("1.35")),
            DecisionGate(key="evidence_conflict", label="证据冲突上限", passed=conflict < Decimal("0.30"), observed=conflict, required=Decimal("0.30")),
            DecisionGate(key="confidence", label="结构置信度", passed=confidence >= 62, observed=Decimal(confidence), required=Decimal("62")),
            DecisionGate(key="cross_exchange", label="跨交易所确认", passed=cross_exchange >= Decimal("0.5"), observed=cross_exchange, required=Decimal("0.5")),
            DecisionGate(key="historical_calibration", label=calibration_label, passed=calibration.status != "DEGRADED", observed=calibration.absolute_error, required=Decimal("0.12")),
        )
        tradeable = all(gate.passed for gate in gates)
        directional_flow = flow * (ONE if direction is Direction.LONG else Decimal("-1"))
        directional_derivatives = derivatives * (ONE if direction is Direction.LONG else Decimal("-1"))
        return SignalAnalysis(
            opportunity_score=opportunity_score,
            confidence=confidence,
            p_tp_before_sl=probability.quantize(Decimal("0.001")),
            expected_value=expected_value.quantize(Decimal("0.001")),
            evidence_conflict=conflict.quantize(Decimal("0.001")),
            is_tradeable=tradeable,
            market_regime=regime,
            signal_type=signal_type,
            smart_money_bias=_smart_money_bias(snapshot),
            derivatives_bias=_bias(directional_derivatives),
            order_flow_bias=_bias(directional_flow),
            news_bias="UNAVAILABLE",
            calibration=calibration,
            decision=SignalDecision(outcome="TRADE" if tradeable else "NO_TRADE", gates=gates),
        )

    @staticmethod
    def _trend(snapshot: MarketSnapshot) -> Decimal:
        values = [_d(snapshot, key) for key in ("trend_4h", "trend_1h", "setup_15m", "trigger_5m")]
        return max(Decimal("-1"), min(ONE, sum(values, ZERO) / Decimal(len(values))))

    @staticmethod
    def _flow(snapshot: MarketSnapshot) -> Decimal:
        aggressive = _d(snapshot, "aggressive_flow_imbalance")
        depth = _d(snapshot, "depth_imbalance")
        persistence = _clip(_d(snapshot, "flow_persistence"))
        impact = _d(snapshot, "price_impact_bps") / Decimal("20")
        return max(Decimal("-1"), min(ONE, (aggressive * Decimal("0.50") + depth * Decimal("0.25") + impact * Decimal("0.25")) * (Decimal("0.5") + persistence / Decimal("2"))))

    @staticmethod
    def _derivatives(snapshot: MarketSnapshot, trend: Decimal) -> Decimal:
        oi = _d(snapshot, "oi_change_ratio")
        funding = snapshot.funding_rate
        oi_support = _clip(abs(oi) / Decimal("0.06")) * (ONE if trend * oi >= ZERO else Decimal("-1"))
        crowded = _clip(abs(funding) / Decimal("0.0015"))
        contrarian = -trend * crowded * Decimal("0.30")
        return max(Decimal("-1"), min(ONE, oi_support + contrarian))

    @staticmethod
    def _anomaly(snapshot: MarketSnapshot, trend: Decimal) -> Decimal:
        volume = _clip((_d(snapshot, "volume_acceleration", "1") - ONE) / Decimal("1.5"))
        volatility = _d(snapshot, "atr_percentile", "50")
        stable = ONE if volatility <= Decimal("55") else Decimal("0.35")
        return trend * volume * stable

    @staticmethod
    def _regime(snapshot: MarketSnapshot, trend: Decimal, anomaly: Decimal) -> str:
        if abs(_d(snapshot, "oi_change_ratio")) >= Decimal("0.06") and abs(_d(snapshot, "price_impact_bps")) >= Decimal("12"):
            return "SQUEEZE"
        if abs(trend) >= Decimal("0.65") and abs(anomaly) >= Decimal("0.25"):
            return "TREND"
        if _d(snapshot, "atr_percentile", "50") >= Decimal("75"):
            return "VOLATILE"
        return "RANGE"

    @staticmethod
    def _weights(regime: str) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        if regime == "TREND":
            return (Decimal("0.30"), Decimal("0.29"), Decimal("0.20"), Decimal("0.11"), Decimal("0.10"))
        if regime == "SQUEEZE":
            return (Decimal("0.16"), Decimal("0.32"), Decimal("0.29"), Decimal("0.13"), Decimal("0.10"))
        return (Decimal("0.22"), Decimal("0.28"), Decimal("0.23"), Decimal("0.17"), Decimal("0.10"))

    @staticmethod
    def _side_score(
        side: Decimal,
        trend: Decimal,
        flow: Decimal,
        derivatives: Decimal,
        anomaly: Decimal,
        cross_exchange: Decimal,
        weights: tuple[Decimal, Decimal, Decimal, Decimal, Decimal],
    ) -> Decimal:
        trend_weight, flow_weight, derivatives_weight, anomaly_weight, cross_weight = weights
        directional = (
            _clip(side * trend) * trend_weight
            + _clip(side * flow) * flow_weight
            + _clip(side * derivatives) * derivatives_weight
            + _clip(side * anomaly) * anomaly_weight
            + cross_exchange * cross_weight
        )
        return _clip(directional)

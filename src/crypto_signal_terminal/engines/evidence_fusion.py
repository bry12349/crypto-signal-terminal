from __future__ import annotations

from decimal import Decimal

from crypto_signal_terminal.domain.models import AssetClass, CalibrationState, DecisionGate, Direction, MarketSnapshot, SignalAnalysis, SignalDecision


ZERO = Decimal("0")
ONE = Decimal("1")
MODEL_VERSION = "0.7.0"


def _d(snapshot: MarketSnapshot, key: str, default: str = "0") -> Decimal:
    try:
        return Decimal(str(snapshot.features.get(key, default)))
    except Exception:
        return Decimal(default)


def _clip(value: Decimal, low: Decimal = ZERO, high: Decimal = ONE) -> Decimal:
    return max(low, min(high, value))


def _signed(value: Decimal) -> Decimal:
    return _clip(value, Decimal("-1"), ONE)


def _bias(value: Decimal, *, threshold: Decimal = Decimal("0.12")) -> str:
    if value >= threshold:
        return "BULLISH"
    if value <= -threshold:
        return "BEARISH"
    return "NEUTRAL"


def asset_profile(symbol: str) -> str:
    if symbol == "BTCUSDT":
        return "BTC"
    if symbol == "ETHUSDT":
        return "ETH"
    return "ALT"


def _smart_money(snapshot: MarketSnapshot) -> tuple[Decimal | None, str]:
    """Never relabel ordinary CEX order flow as attributed smart money."""
    if snapshot.features.get("smart_money_source") != "public_onchain_wallet":
        return None, "UNAVAILABLE"
    value = _signed(_d(snapshot, "onchain_smart_money_flow"))
    return value, _bias(value)


def _narrative(snapshot: MarketSnapshot) -> tuple[Decimal | None, str, tuple[str, ...]]:
    bias = str(snapshot.features.get("narrative_bias", "UNAVAILABLE"))
    independent = int(snapshot.features.get("narrative_independent_sources", 0))
    if independent < 2 or bias not in {"BULLISH", "BEARISH", "NEUTRAL"}:
        return None, bias, ()
    raw_sources = str(snapshot.features.get("narrative_sources", ""))
    sources = tuple(item for item in raw_sources.split("|") if item)
    return _signed(_d(snapshot, "narrative_score")), bias, sources


class EvidenceFusion:
    """Asset-specific, explainable fusion for a TP-before-SL estimate.

    The output is a conservative model estimate, not a claimed win rate. Public
    opinions and wallet observations are capped supporting factors; execution
    still requires every market-quality and calibration gate to pass.
    """

    _WEIGHTS = {
        "BTC": {"trend": Decimal("0.31"), "flow": Decimal("0.24"), "derivatives": Decimal("0.21"), "anomaly": Decimal("0.08"), "cycle": Decimal("0.08"), "smart": Decimal("0.04"), "narrative": Decimal("0.04")},
        "ETH": {"trend": Decimal("0.28"), "flow": Decimal("0.25"), "derivatives": Decimal("0.22"), "anomaly": Decimal("0.10"), "btc_context": Decimal("0.08"), "smart": Decimal("0.03"), "narrative": Decimal("0.04")},
        "ALT": {"trend": Decimal("0.17"), "flow": Decimal("0.22"), "derivatives": Decimal("0.20"), "anomaly": Decimal("0.13"), "btc_context": Decimal("0.13"), "smart": Decimal("0.08"), "narrative": Decimal("0.07")},
    }
    _THRESHOLDS = {
        "BTC": (Decimal("0.57"), Decimal("64"), Decimal("1.35"), Decimal("0.28")),
        "ETH": (Decimal("0.58"), Decimal("65"), Decimal("1.35"), Decimal("0.27")),
        "ALT": (Decimal("0.60"), Decimal("68"), Decimal("1.35"), Decimal("0.24")),
    }

    def evaluate(self, snapshot: MarketSnapshot, *, direction: Direction, reward_to_risk: Decimal, signal_type: str, calibration: CalibrationState | None = None, profile_override: str | None = None) -> SignalAnalysis:
        profile = profile_override or (snapshot.asset_class.value if snapshot.asset_class is not AssetClass.CRYPTO else asset_profile(snapshot.symbol))
        if profile in {"COMMODITY", "US_EQUITY"}:
            return self._evaluate_tradfi(snapshot, profile=profile, direction=direction, reward_to_risk=reward_to_risk, signal_type=signal_type, calibration=calibration)
        trend = self._trend(snapshot, profile)
        flow = self._flow(snapshot)
        derivatives = self._derivatives(snapshot, trend)
        anomaly = self._anomaly(snapshot, trend)
        smart, smart_bias = _smart_money(snapshot)
        narrative, narrative_bias, narrative_sources = _narrative(snapshot)
        factors: dict[str, Decimal | None] = {"trend": trend, "flow": flow, "derivatives": derivatives, "anomaly": anomaly, "smart": smart, "narrative": narrative}
        if profile == "BTC":
            factors["cycle"] = _signed(_d(snapshot, "btc_cycle_bias")) if "btc_cycle_bias" in snapshot.features else None
        else:
            factors["btc_context"] = _signed(_d(snapshot, "btc_regime_score")) if "btc_regime_score" in snapshot.features else ZERO

        side = ONE if direction is Direction.LONG else Decimal("-1")
        support = ZERO
        opposition = ZERO
        observed_weight = ZERO
        for name, value in factors.items():
            if value is None:
                continue
            weight = self._WEIGHTS[profile][name]
            observed_weight += weight
            directional = side * value
            support += weight * max(ZERO, directional)
            opposition += weight * max(ZERO, -directional)

        directional_total = support + opposition
        alignment = support / directional_total if directional_total else Decimal("0.5")
        strength = directional_total / observed_weight if observed_weight else ZERO
        conflict = min(support, opposition) / max(support, opposition, Decimal("0.0001"))
        cross_exchange = _clip(Decimal(snapshot.peer_confirmations - 1) / Decimal("2"))
        raw_probability = _clip(Decimal("0.30") + alignment * Decimal("0.28") + strength * Decimal("0.12") + cross_exchange * Decimal("0.04") - conflict * Decimal("0.16"), Decimal("0.05"), Decimal("0.85"))
        calibration = calibration or CalibrationState(settled=0, mean_predicted=ZERO, observed_win_rate=ZERO, absolute_error=ZERO, status="INSUFFICIENT")
        probability = self._calibrated_probability(raw_probability, calibration)
        confidence = int(_clip(alignment * Decimal("0.70") + strength * Decimal("0.30") - conflict * Decimal("0.25")) * Decimal("100"))
        opportunity_score = int(_clip((support - opposition + observed_weight) / max(observed_weight * Decimal("2"), Decimal("0.0001"))) * Decimal("100"))
        expected_value = (probability * reward_to_risk) - (ONE - probability) - Decimal("0.08")
        regime = self._regime(snapshot, trend)
        probability_floor, confidence_floor, rr_floor, conflict_ceiling = self._THRESHOLDS[profile]
        calibration_label = {"INSUFFICIENT": "历史校准：样本不足（概率已封顶）", "VALIDATED": "历史校准：已通过并参与概率收缩", "DEGRADED": "历史校准：偏差或 Brier 超限"}[calibration.status]
        gates = [
            DecisionGate(key="tp_before_sl", label="TP 先于 SL 概率", passed=probability >= probability_floor, observed=probability, required=probability_floor),
            DecisionGate(key="expected_value", label="净期望值", passed=expected_value > ZERO, observed=expected_value, required=ZERO),
            DecisionGate(key="reward_to_risk", label="盈亏比", passed=reward_to_risk >= rr_floor, observed=reward_to_risk, required=rr_floor),
            DecisionGate(key="evidence_conflict", label="证据冲突上限", passed=conflict < conflict_ceiling, observed=conflict, required=conflict_ceiling),
            DecisionGate(key="confidence", label=f"{profile} 结构置信度", passed=confidence >= confidence_floor, observed=Decimal(confidence), required=confidence_floor),
            DecisionGate(key="cross_exchange", label="跨交易所确认", passed=cross_exchange >= Decimal("0.5"), observed=cross_exchange, required=Decimal("0.5")),
            DecisionGate(key="historical_calibration", label=calibration_label, passed=calibration.status != "DEGRADED", observed=calibration.absolute_error, required=Decimal("0.12")),
        ]
        if profile == "ALT":
            btc_context = _signed(_d(snapshot, "btc_regime_score"))
            btc_alignment = side * btc_context
            spread = _d(snapshot, "spread_bps", str((snapshot.ask - snapshot.bid) / snapshot.price * Decimal("10000")))
            slippage = _d(snapshot, "slippage_bps_1000")
            market_quality = max(spread / Decimal("12"), slippage / Decimal("12"), Decimal("5000000") / max(snapshot.volume_24h, ONE))
            gates.extend((
                DecisionGate(key="btc_regime_alignment", label="BTC 风险环境未强烈逆向", passed=btc_alignment >= Decimal("-0.15"), observed=btc_alignment, required=Decimal("-0.15")),
                DecisionGate(key="alt_market_quality", label="山寨币流动性质量", passed=market_quality <= ONE, observed=market_quality, required=ONE),
            ))

        tradeable = all(gate.passed for gate in gates)
        return SignalAnalysis(
            opportunity_score=opportunity_score, confidence=confidence,
            p_tp_before_sl=probability.quantize(Decimal("0.001")), expected_value=expected_value.quantize(Decimal("0.001")),
            evidence_conflict=conflict.quantize(Decimal("0.001")), is_tradeable=tradeable,
            market_regime=regime, signal_type=signal_type, smart_money_bias=smart_bias,
            derivatives_bias=_bias(side * derivatives), order_flow_bias=_bias(side * flow),
            news_bias=str(snapshot.features.get("news_bias", "UNAVAILABLE")),
            asset_profile=profile, model_version=MODEL_VERSION, narrative_bias=narrative_bias,
            narrative_score=(narrative or ZERO).quantize(Decimal("0.001")), narrative_sources=narrative_sources,
            calibration=calibration, decision=SignalDecision(outcome="TRADE" if tradeable else "NO_TRADE", gates=tuple(gates)),
        )

    def _evaluate_tradfi(
        self,
        snapshot: MarketSnapshot,
        *,
        profile: str,
        direction: Direction,
        reward_to_risk: Decimal,
        signal_type: str,
        calibration: CalibrationState | None,
    ) -> SignalAnalysis:
        """Independent fusion for Bybit TradFi perpetuals.

        Commodities and US equities deliberately use no crypto funding/OI
        factor. Their probability is driven by the model-specific feature
        contract emitted by the TradFi adapter and is blocked when market
        session, event, or liquidity quality is not verifiable.
        """
        def value(key: str, default: str = "0") -> Decimal:
            return _d(snapshot, key, default)

        side = ONE if direction is Direction.LONG else Decimal("-1")
        if profile == "COMMODITY":
            trend = _signed(value("trend_1d") * Decimal("0.35") + value("trend_4h") * Decimal("0.35") + value("trend_1h") * Decimal("0.20") + value("trigger_5m") * Decimal("0.10"))
            macro = _signed(value("macro_score"))
            term = _signed(value("term_structure_score"))
            flow = _signed(value("commodity_flow", str(value("aggressive_flow_imbalance"))))
            volatility = _clip(ONE - abs(value("atr_percentile", "50") - Decimal("50")) / Decimal("50"))
            event_risk = _clip(value("event_risk"))
            liquidity = _clip(value("session_liquidity", "1"))
            weights = ((trend, Decimal("0.32")), (macro, Decimal("0.24")), (term, Decimal("0.16")), (flow, Decimal("0.12")), (volatility * side, Decimal("0.08")), ((ONE - event_risk) * liquidity, Decimal("0.08")))
            model_version = "0.8.0-commodity"
            market_regime = "MACRO_TREND" if abs(trend) >= Decimal("0.55") else "MACRO_RANGE"
            quality = max(value("spread_bps") / Decimal("8"), value("slippage_bps_1000") / Decimal("8"), (ONE - liquidity))
            extra = [
                DecisionGate(key="commodity_session", label="商品交易时段与流动性", passed=liquidity >= Decimal("0.55"), observed=liquidity, required=Decimal("0.55")),
                DecisionGate(key="commodity_event_risk", label="宏观事件风险可控", passed=event_risk <= Decimal("0.45"), observed=event_risk, required=Decimal("0.45")),
                DecisionGate(key="commodity_market_quality", label="商品点差与滑点", passed=quality <= ONE, observed=quality, required=ONE),
            ]
            raw = Decimal("0.27") + sum((weight * max(ZERO, side * factor) for factor, weight in weights), ZERO) * Decimal("0.52") + sum((weight for factor, weight in weights if side * factor > Decimal("0.18")), ZERO) * Decimal("0.08")
            conflict = min(sum((weight * max(ZERO, side * factor * Decimal("-1")) for factor, weight in weights), ZERO), sum((weight * max(ZERO, side * factor) for factor, weight in weights), ZERO)) / max(sum((weight * abs(factor) for factor, weight in weights), ZERO), Decimal("0.0001"))
            derivatives = term
            flow_bias = flow
            smart_bias = "UNAVAILABLE"
        else:
            trend = _signed(value("trend_4h") * Decimal("0.40") + value("trend_1h") * Decimal("0.30") + value("trigger_5m") * Decimal("0.12") + value("relative_strength") * Decimal("0.18"))
            market = _signed(value("index_regime"))
            relative = _signed(value("relative_strength"))
            flow = _signed(value("equity_flow", str(value("aggressive_flow_imbalance"))))
            volatility = _clip(ONE - abs(value("atr_percentile", "50") - Decimal("50")) / Decimal("50"))
            session = _clip(value("session_liquidity", "1"))
            weights = ((trend, Decimal("0.28")), (market, Decimal("0.22")), (relative, Decimal("0.20")), (flow, Decimal("0.14")), (volatility * side, Decimal("0.08")), (session, Decimal("0.08")))
            model_version = "0.8.0-us-equity"
            market_regime = "INDEX_TREND" if abs(market) >= Decimal("0.55") else "INDEX_RANGE"
            earnings_risk = _clip(value("earnings_risk"))
            gap_risk = _clip(value("gap_risk"))
            quality = max(value("spread_bps") / Decimal("5"), value("slippage_bps_1000") / Decimal("6"), (ONE - session))
            extra = [
                DecisionGate(key="equity_session", label="美股合约流动性时段", passed=session >= Decimal("0.55"), observed=session, required=Decimal("0.55")),
                DecisionGate(key="earnings_risk", label="财报事件风险可控", passed=earnings_risk <= Decimal("0.45"), observed=earnings_risk, required=Decimal("0.45")),
                DecisionGate(key="gap_risk", label="开盘跳空风险可控", passed=gap_risk <= Decimal("0.60"), observed=gap_risk, required=Decimal("0.60")),
                DecisionGate(key="equity_market_quality", label="股票点差与滑点", passed=quality <= ONE, observed=quality, required=ONE),
            ]
            raw = Decimal("0.27") + sum((weight * max(ZERO, side * factor) for factor, weight in weights), ZERO) * Decimal("0.52") + sum((weight for factor, weight in weights if side * factor > Decimal("0.18")), ZERO) * Decimal("0.08")
            conflict = min(sum((weight * max(ZERO, side * factor * Decimal("-1")) for factor, weight in weights), ZERO), sum((weight * max(ZERO, side * factor) for factor, weight in weights), ZERO)) / max(sum((weight * abs(factor) for factor, weight in weights), ZERO), Decimal("0.0001"))
            derivatives = market
            flow_bias = flow
            smart_bias = "UNAVAILABLE"

        calibration = calibration or CalibrationState(settled=0, mean_predicted=ZERO, observed_win_rate=ZERO, absolute_error=ZERO, status="INSUFFICIENT")
        probability = self._calibrated_probability(_clip(raw, Decimal("0.05"), Decimal("0.85")), calibration)
        strength = sum((weight * abs(factor) for factor, weight in weights), ZERO)
        confidence = int(_clip(Decimal("0.45") * strength + Decimal("0.55") * max(ZERO, side * trend)) * Decimal("100"))
        opportunity_score = int(_clip(Decimal("0.5") + side * trend * Decimal("0.35") + side * flow_bias * Decimal("0.15")) * Decimal("100"))
        expected_value = probability * reward_to_risk - (ONE - probability) - Decimal("0.08")
        probability_floor = Decimal("0.62") if profile == "COMMODITY" else Decimal("0.63")
        confidence_floor = Decimal("66") if profile == "COMMODITY" else Decimal("68")
        rr_floor = Decimal("1.50") if profile == "COMMODITY" else Decimal("1.60")
        gates = [
            DecisionGate(key="tp_before_sl", label="TP 先于 SL 概率", passed=probability >= probability_floor, observed=probability, required=probability_floor),
            DecisionGate(key="expected_value", label="净期望值", passed=expected_value > ZERO, observed=expected_value, required=ZERO),
            DecisionGate(key="reward_to_risk", label="盈亏比", passed=reward_to_risk >= rr_floor, observed=reward_to_risk, required=rr_floor),
            DecisionGate(key="evidence_conflict", label="证据冲突上限", passed=conflict < Decimal("0.30"), observed=conflict, required=Decimal("0.30")),
            DecisionGate(key="confidence", label=f"{profile} 结构置信度", passed=Decimal(confidence) >= confidence_floor, observed=Decimal(confidence), required=confidence_floor),
            DecisionGate(key="cross_exchange", label="独立价格确认", passed=snapshot.peer_confirmations >= 2, observed=Decimal(snapshot.peer_confirmations), required=Decimal("2")),
            DecisionGate(key="historical_calibration", label="历史校准未降级", passed=calibration.status != "DEGRADED", observed=calibration.absolute_error, required=Decimal("0.12"),),
            *extra,
        ]
        return SignalAnalysis(
            opportunity_score=opportunity_score, confidence=confidence,
            p_tp_before_sl=probability.quantize(Decimal("0.001")), expected_value=expected_value.quantize(Decimal("0.001")),
            evidence_conflict=_clip(conflict).quantize(Decimal("0.001")), is_tradeable=all(gate.passed for gate in gates),
            market_regime=market_regime, signal_type=signal_type, smart_money_bias=smart_bias,
            derivatives_bias=_bias(side * derivatives), order_flow_bias=_bias(side * flow_bias),
            news_bias="UNAVAILABLE", asset_profile=profile, model_version=model_version,
            narrative_bias="UNAVAILABLE", narrative_score=ZERO, narrative_sources=(), calibration=calibration,
            decision=SignalDecision(outcome="TRADE" if all(gate.passed for gate in gates) else "NO_TRADE", gates=tuple(gates)),
        )

    @staticmethod
    def _calibrated_probability(raw: Decimal, calibration: CalibrationState) -> Decimal:
        if calibration.status == "VALIDATED" and calibration.settled:
            history_weight = min(Decimal("0.60"), Decimal(calibration.settled) / Decimal("200") * Decimal("0.60"))
            return _clip(raw * (ONE - history_weight) + calibration.observed_win_rate * history_weight)
        return min(raw, Decimal("0.68"))

    @staticmethod
    def _trend(snapshot: MarketSnapshot, profile: str) -> Decimal:
        continuous = _d(snapshot, "trend_strength_4h") * Decimal("0.38") + _d(snapshot, "trend_strength_1h") * Decimal("0.30") + _d(snapshot, "setup_strength_15m") * Decimal("0.20") + _d(snapshot, "trigger_strength_5m") * Decimal("0.12")
        if any(key in snapshot.features for key in ("trend_strength_4h", "trend_strength_1h")):
            return _signed(continuous)
        values = [_d(snapshot, key) for key in ("trend_4h", "trend_1h", "setup_15m", "trigger_5m")]
        weighting = (Decimal("0.38"), Decimal("0.30"), Decimal("0.20"), Decimal("0.12")) if profile != "ALT" else (Decimal("0.26"), Decimal("0.30"), Decimal("0.26"), Decimal("0.18"))
        return _signed(sum((value * weight for value, weight in zip(values, weighting, strict=True)), ZERO))

    @staticmethod
    def _flow(snapshot: MarketSnapshot) -> Decimal:
        aggressive = _d(snapshot, "aggressive_flow_imbalance")
        depth = _d(snapshot, "depth_imbalance")
        persistence = _clip(_d(snapshot, "flow_persistence"))
        impact = _signed(_d(snapshot, "price_impact_bps") / Decimal("20"))
        return _signed((aggressive * Decimal("0.50") + depth * Decimal("0.25") + impact * Decimal("0.25")) * (Decimal("0.5") + persistence / Decimal("2")))

    @staticmethod
    def _derivatives(snapshot: MarketSnapshot, trend: Decimal) -> Decimal:
        oi = _d(snapshot, "oi_change_ratio")
        oi_force = _clip(abs(oi) / Decimal("0.06"))
        crowded = _clip(abs(snapshot.funding_rate) / Decimal("0.0015"))
        crowd_direction = ONE if snapshot.funding_rate >= ZERO else Decimal("-1")
        trend_direction = ONE if trend >= ZERO else Decimal("-1")
        oi_with_price = trend_direction * oi_force * (ONE if oi >= ZERO else Decimal("-0.50"))
        return _signed(oi_with_price - crowd_direction * crowded * Decimal("0.25"))

    @staticmethod
    def _anomaly(snapshot: MarketSnapshot, trend: Decimal) -> Decimal:
        volume = _clip((_d(snapshot, "volume_acceleration", "1") - ONE) / Decimal("1.5"))
        stable = ONE if _d(snapshot, "atr_percentile", "50") <= Decimal("55") else Decimal("0.35")
        return _signed(trend * volume * stable)

    @staticmethod
    def _regime(snapshot: MarketSnapshot, trend: Decimal) -> str:
        if abs(_d(snapshot, "oi_change_ratio")) >= Decimal("0.06") and abs(_d(snapshot, "price_impact_bps")) >= Decimal("12"):
            return "SQUEEZE"
        if abs(trend) >= Decimal("0.65") and _d(snapshot, "volume_acceleration", "1") >= Decimal("1.5"):
            return "TREND"
        if _d(snapshot, "atr_percentile", "50") >= Decimal("75"):
            return "VOLATILE"
        return "RANGE"

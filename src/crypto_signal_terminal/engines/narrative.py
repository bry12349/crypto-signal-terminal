from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import re

from crypto_signal_terminal.domain.models import NarrativeAssessment, NarrativeObservation


ZERO = Decimal("0")
ONE = Decimal("1")


def _clip(value: Decimal, low: Decimal = ZERO, high: Decimal = ONE) -> Decimal:
    return max(low, min(high, value))


class NarrativeEngine:
    """Conservatively aggregate attributable public opinions.

    One loud account is deliberately insufficient. The returned score is capped
    because text sentiment is supporting evidence, not a substitute for price,
    liquidity, derivatives, or independently settled performance.
    """

    _MAX_AGE = {
        "BTC": timedelta(hours=24),
        "ETH": timedelta(hours=12),
        "ALT": timedelta(hours=6),
    }
    _HALF_LIFE_HOURS = {"BTC": 8.0, "ETH": 5.0, "ALT": 2.5}
    _KIND_CAP = {
        "FORUM": Decimal("0.35"),
        "ANALYST": Decimal("0.60"),
        "COPY_TRADER": Decimal("0.70"),
        "NEWS": Decimal("0.45"),
    }

    @staticmethod
    def asset_profile(symbol: str) -> str:
        if symbol == "BTCUSDT":
            return "BTC"
        if symbol == "ETHUSDT":
            return "ETH"
        return "ALT"

    @staticmethod
    def _skill_multiplier(item: NarrativeObservation) -> Decimal:
        # Unsettled reputations are shrunk to neutral. Once at least 20 calls
        # settle, a beta prior prevents small samples and lucky streaks from
        # receiving extreme weight.
        if item.historical_hit_rate is None or item.settled_calls < 20:
            return Decimal("0.65")
        wins = item.historical_hit_rate * Decimal(item.settled_calls)
        posterior = (wins + Decimal("10")) / Decimal(item.settled_calls + 20)
        return _clip(Decimal("0.50") + posterior, Decimal("0.65"), Decimal("1.25"))

    def assess(
        self,
        symbol: str,
        observations: tuple[NarrativeObservation, ...] | list[NarrativeObservation],
        *,
        as_of: datetime,
    ) -> NarrativeAssessment:
        profile = self.asset_profile(symbol)
        latest_by_source: dict[str, NarrativeObservation] = {}
        seen_text: set[str] = set()
        for item in observations:
            if symbol not in item.symbols or item.published_at > as_of:
                continue
            if as_of - item.published_at > self._MAX_AGE[profile]:
                continue
            fingerprint = re.sub(r"\W+", " ", item.text.lower()).strip()
            if fingerprint and fingerprint in seen_text:
                continue
            if fingerprint:
                seen_text.add(fingerprint)
            previous = latest_by_source.get(item.source_id)
            if previous is None or item.published_at > previous.published_at:
                latest_by_source[item.source_id] = item
        if not latest_by_source:
            return NarrativeAssessment(bias="UNAVAILABLE", score=ZERO, confidence=ZERO, independent_sources=0)

        weighted = ZERO
        total_weight = ZERO
        for item in latest_by_source.values():
            age_hours = Decimal(str(max(0.0, (as_of - item.published_at).total_seconds() / 3600)))
            decay = Decimal(str(0.5 ** (float(age_hours) / self._HALF_LIFE_HOURS[profile])))
            prior = min(item.source_prior, self._KIND_CAP[item.source_kind])
            weight = prior * item.confidence * decay * self._skill_multiplier(item)
            weighted += item.stance * weight
            total_weight += weight

        count = len(latest_by_source)
        sources = tuple(sorted(item.source_name for item in latest_by_source.values()))
        if count < 2 or total_weight <= ZERO:
            return NarrativeAssessment(
                bias="UNCONFIRMED", score=ZERO,
                confidence=_clip(total_weight / Decimal("1.5")),
                independent_sources=count, sources=sources,
            )
        raw = weighted / total_weight
        # Opinion data can move a model at the margin, never dominate it.
        score = _clip(raw, Decimal("-0.35"), Decimal("0.35"))
        confidence = _clip(total_weight / Decimal("1.2"))
        bias = "BULLISH" if score >= Decimal("0.12") else "BEARISH" if score <= Decimal("-0.12") else "NEUTRAL"
        return NarrativeAssessment(
            bias=bias, score=score.quantize(Decimal("0.001")), confidence=confidence.quantize(Decimal("0.001")),
            independent_sources=count, sources=sources,
        )

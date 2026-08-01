from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from crypto_signal_terminal.domain.models import MarketSnapshot


class FeatureSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    spread_bps: Decimal
    depth_imbalance: Decimal
    aggressive_flow_imbalance: Decimal
    oi_change_ratio: Decimal
    funding_rate: Decimal
    atr_percentile: Decimal
    volume_acceleration: Decimal
    trend_4h: int
    trend_1h: int
    setup_15m: int
    trigger_5m: int
    absorption: Decimal


def _imbalance(left: Decimal, right: Decimal) -> Decimal:
    total = left + right
    return Decimal("0") if total == 0 else (left - right) / total


def _d(value: object, default: str = "0") -> Decimal:
    return Decimal(str(value if value is not None else default))


def calculate_features(snapshot: MarketSnapshot) -> FeatureSet:
    mid = (snapshot.bid + snapshot.ask) / Decimal("2")
    raw = snapshot.features
    bid_size = _d(raw.get("bid_size"))
    ask_size = _d(raw.get("ask_size"))
    buys = _d(raw.get("buy_volume"))
    sells = _d(raw.get("sell_volume"))
    previous_oi = _d(raw.get("previous_open_interest"))
    oi_change = Decimal("0") if previous_oi == 0 else (snapshot.open_interest - previous_oi) / previous_oi
    return FeatureSet(
        spread_bps=(snapshot.ask - snapshot.bid) / mid * Decimal("10000"),
        depth_imbalance=_imbalance(bid_size, ask_size),
        aggressive_flow_imbalance=_imbalance(buys, sells),
        oi_change_ratio=oi_change,
        funding_rate=snapshot.funding_rate,
        atr_percentile=_d(raw.get("atr_percentile"), "50"),
        volume_acceleration=_d(raw.get("volume_acceleration"), "1"),
        trend_4h=int(raw.get("trend_4h", 0)),
        trend_1h=int(raw.get("trend_1h", 0)),
        setup_15m=int(raw.get("setup_15m", 0)),
        trigger_5m=int(raw.get("trigger_5m", 0)),
        absorption=_d(raw.get("absorption")),
    )

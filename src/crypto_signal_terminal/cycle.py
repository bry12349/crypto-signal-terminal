"""Deterministic BTC halving-cycle context; it is not a price forecast."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


HALVING_INTERVAL = 210_000
BULL_HALF = 78_750
BULL_LENGTH = BULL_HALF * 2
BEAR_LENGTH = HALVING_INTERVAL - BULL_LENGTH


@dataclass(frozen=True)
class CycleState:
    height: int
    index: Decimal
    phase: str
    market_bias: str
    blocks_to_halving: int


def wave_index_at(height: int) -> Decimal:
    """Return the block-native Wolfy Wave Index in the inclusive range [0, 1]."""
    phase = (height + BULL_HALF) % HALVING_INTERVAL
    if phase < BULL_LENGTH:
        return Decimal(phase) / Decimal(BULL_LENGTH)
    return Decimal(1) - Decimal(phase - BULL_LENGTH) / Decimal(BEAR_LENGTH)


def cycle_state_at(height: int) -> CycleState:
    index = wave_index_at(height)
    phase_position = (height + BULL_HALF) % HALVING_INTERVAL
    bullish = phase_position < BULL_LENGTH
    progress = index if bullish else Decimal(1) - index
    if bullish:
        phase = "BULL_EARLY" if progress < Decimal("0.33") else "BULL_MID" if progress < Decimal("0.67") else "BULL_LATE"
        market_bias = "BULLISH"
    else:
        phase = "BEAR_EARLY" if progress < Decimal("0.33") else "BEAR_MID" if progress < Decimal("0.67") else "BEAR_LATE"
        market_bias = "BEARISH"
    nearest_halving = round(height / HALVING_INTERVAL) * HALVING_INTERVAL
    return CycleState(height=height, index=index, phase=phase, market_bias=market_bias, blocks_to_halving=nearest_halving - height)

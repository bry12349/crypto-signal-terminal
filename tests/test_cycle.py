from decimal import Decimal

from crypto_signal_terminal.cycle import cycle_state_at, wave_index_at


def test_wave_index_is_half_at_every_halving_height() -> None:
    assert wave_index_at(840_000) == Decimal("0.5")
    assert wave_index_at(1_050_000) == Decimal("0.5")


def test_cycle_state_labels_bull_early_and_bull_late_from_block_phase() -> None:
    assert cycle_state_at(840_000 - 70_000).phase == "BULL_EARLY"
    assert cycle_state_at(840_000 + 70_000).phase == "BULL_LATE"


def test_cycle_state_labels_bear_mid_after_bull_segment() -> None:
    state = cycle_state_at(840_000 + 78_750 + 26_250)
    assert state.phase == "BEAR_MID"
    assert state.market_bias == "BEARISH"
    assert state.index == Decimal("0.5")

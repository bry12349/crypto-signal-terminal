from crypto_signal_terminal.main import _market, build_demo_state
from crypto_signal_terminal.market.scanner import LiveMarketScanner


async def test_scanner_refreshes_native_and_smart_money_opportunities() -> None:
    snapshots = {
        "BTCUSDT": _market(
            "BTCUSDT", "67000", trend_4h=1, trend_1h=1, setup_15m=1,
            trigger_5m=1, aggressive_flow_imbalance="0.6",
        ),
        "SOLUSDT": _market(
            "SOLUSDT", "146", atr_percentile=10, volume_acceleration="2",
            oi_change_ratio="0.08", aggressive_flow_imbalance="-0.7",
            depth_imbalance="-0.3", trigger_5m=-1, spread_bps="3",
            large_trade_count=8, flow_persistence="0.8", price_impact_bps="15",
            absorption="0.2",
        ),
    }

    class Market:
        async def snapshot(self, symbol: str): return snapshots[symbol]

    state = build_demo_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=tuple(snapshots))
    await scanner.scan_once()
    assert state.mode == "live"
    assert {item.symbol for item in state.opportunities} == {"BTCUSDT", "SOLUSDT"}
    assert state.smart_money[0].symbol == "SOLUSDT"
    assert all(item.signal.account_id != "demo" for item in state.confirmations)

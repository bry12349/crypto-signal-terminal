from crypto_signal_terminal.main import _market, build_demo_state
from crypto_signal_terminal.main import build_live_state
from decimal import Decimal

from crypto_signal_terminal.adapters.binance_web3 import OnchainWalletFlow
from crypto_signal_terminal.domain.models import Candle, Direction, LifecycleState, SmartMoneyKind
from crypto_signal_terminal.market.scanner import LiveMarketScanner, rank_opportunities
from crypto_signal_terminal.storage import AuditStore
from crypto_signal_terminal.engines.signal_ledger import SignalOutcome, SignalRecord


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


def test_ranking_places_an_actionable_positive_expectancy_signal_before_a_higher_confidence_watch_item() -> None:
    actionable = next(item for item in build_demo_state().opportunities if item.order_plan is not None)
    watch_only = actionable.model_copy(update={
        "id": "watch-only",
        "state": LifecycleState.ARMED,
        "confidence": 99,
        "order_plan": None,
        "analysis": actionable.analysis.model_copy(update={"is_tradeable": False, "expected_value": Decimal("-0.1")}),
    })

    ranked = rank_opportunities([watch_only, actionable])

    assert ranked[0].id == actionable.id


async def test_partial_watchlist_failure_is_visible_as_degraded() -> None:
    class Market:
        async def snapshot(self, symbol: str):
            if symbol == "ETHUSDT":
                raise RuntimeError("upstream timeout")
            return _market(
                symbol, "67000", trend_4h=1, trend_1h=1, setup_15m=1,
                trigger_5m=1, aggressive_flow_imbalance="0.6",
            )

    state = build_demo_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT", "ETHUSDT"))
    assert await scanner.scan_once() == 1
    assert state.market_health == "degraded"
    health = state.market_health_registry.snapshot()
    assert health["symbols"]["BTCUSDT"]["status"] == "healthy"
    assert health["symbols"]["ETHUSDT"]["status"] == "unavailable"
    assert health["symbols"]["ETHUSDT"]["reason"] == "upstream_error"


async def test_stale_exchange_timestamps_cannot_report_healthy_market() -> None:
    class Market:
        async def snapshot(self, symbol: str):
            current = _market(symbol, "67000", trend_4h=1, trend_1h=1, setup_15m=1)
            return current.model_copy(update={"data_health": current.data_health.model_copy(update={"healthy": False})})

    state = build_demo_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT",))
    assert await scanner.scan_once() == 1
    assert state.market_health == "degraded"


async def test_total_market_failure_clears_stale_demo_opportunities() -> None:
    class Market:
        async def snapshot(self, symbol: str):
            raise TimeoutError("offline")

    state = build_demo_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT", "SOLUSDT"))

    assert await scanner.scan_once() == 0
    assert state.mode == "live"
    assert state.opportunities == []
    assert state.smart_money == []
    assert state.market_health == "degraded"


async def test_wallet_tracking_survives_when_all_cex_market_snapshots_fail() -> None:
    class Market:
        async def snapshot(self, symbol: str):
            raise TimeoutError("offline")

    class WalletTracker:
        async def observe(self):
            return (OnchainWalletFlow(
                wallet="0xabc",
                label="链上高手",
                token_symbol="SOL",
                direction=Direction.LONG,
                notional_delta=Decimal("500000"),
                score=84,
                is_baseline=True,
            ),)

    state = build_live_state()
    scanner = LiveMarketScanner(
        state=state,
        market=Market(),
        watchlist=("BTCUSDT",),
        wallet_tracker=WalletTracker(),
    )

    assert await scanner.scan_once() == 0
    assert [item.wallet for item in state.smart_money] == ["0xabc"]
    assert state.opportunities == []


async def test_wallet_roster_is_not_cleared_during_tracker_cache_interval() -> None:
    class Market:
        async def snapshot(self, symbol: str):
            return _market(symbol, "67000", trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1)

    class WalletTracker:
        calls = 0

        async def observe(self):
            self.calls += 1
            if self.calls > 1:
                return ()
            return (OnchainWalletFlow(
                wallet="0xabc", label="链上高手", token_symbol="SOL", direction=Direction.LONG,
                notional_delta=Decimal("500000"), score=84, is_baseline=True,
            ),)

    state = build_live_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT",), wallet_tracker=WalletTracker())
    await scanner.scan_once()
    await scanner.scan_once()

    assert [item.wallet for item in state.smart_money if item.wallet] == ["0xabc"]


async def test_healthy_market_without_trigger_remains_visible_as_forming_observation() -> None:
    class Market:
        async def snapshot(self, symbol: str):
            return _market(
                symbol, "67000", trend_4h=1, trend_1h=-1, setup_15m=0,
                trigger_5m=0, aggressive_flow_imbalance="0.02",
            )

    state = build_live_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT",))

    assert await scanner.scan_once() == 1
    assert len(state.opportunities) == 1
    observation = state.opportunities[0]
    assert observation.id == "observe:BTCUSDT"
    assert observation.state is LifecycleState.FORMING
    assert observation.order_plan is None
    assert observation.title == "实时市场观察 · 等待触发"
    assert observation.risk == "当前不具备可执行条件，系统不会生成订单建议"


async def test_forming_observation_exposes_actual_multi_timeframe_and_derivatives_values() -> None:
    class Market:
        async def snapshot(self, symbol: str):
            return _market(
                symbol, "67000", trend_4h=-1, trend_1h=-1, setup_15m=1, trigger_5m=-1,
                aggressive_flow_imbalance="-0.36", oi_change_ratio="-0.041", funding_rate="0.0008",
                slippage_bps_1000="4.2",
            )

    state = build_live_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT",))
    await scanner.scan_once()

    evidence = state.opportunities[0].evidence
    assert "4h 偏空 · 1h 偏空 · 15m 偏多 · 5m 偏空" in evidence[1].text
    assert evidence[2].code == "derivatives_live"
    assert "OI -4.10%" in evidence[2].text


async def test_scanner_refreshes_the_altcoin_universe_before_scanning() -> None:
    class Universe:
        async def top_altcoins(self): return ("SOLUSDT", "SUIUSDT")

    class Market:
        async def snapshot(self, symbol: str):
            return _market(symbol, "67000", trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1, aggressive_flow_imbalance="0.6")

    scanner = LiveMarketScanner(state=build_live_state(), market=Market(), universe=Universe())
    assert await scanner.scan_once() == 4
    assert scanner.watchlist == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT")


def test_scanner_uses_fast_refresh_without_unbounded_parallelism() -> None:
    scanner = LiveMarketScanner(state=build_live_state(), market=object(), watchlist=("BTCUSDT",))
    assert scanner.interval_seconds == 5
    assert scanner.max_concurrency == 6


async def test_scanner_records_and_settles_actionable_signal_outcomes(tmp_path) -> None:
    initial = _market(
        "BTCUSDT", "67000", trend_4h=1, trend_1h=1, setup_15m=1,
        trigger_5m=1, aggressive_flow_imbalance="0.6", depth_imbalance="0.2",
        flow_persistence="0.8", oi_change_ratio="0.05", price_impact_bps="12",
    )
    target = initial.model_copy(update={"candles": (
        Candle(timestamp=int(initial.observed_at.timestamp()) + 300, open="67000", high="67650", low="66900", close="67600", volume="10"),
    )})
    snapshots = [initial, target]

    class Market:
        async def snapshot(self, symbol: str): return snapshots.pop(0)

    store = AuditStore(tmp_path / "audit.sqlite3")
    scanner = LiveMarketScanner(state=build_live_state(), market=Market(), watchlist=("BTCUSDT",), audit_store=store)
    await scanner.scan_once()
    assert store.signal_records()[0].outcome.value == "PENDING"

    await scanner.scan_once()
    assert store.signal_records()[0].outcome.value == "TP1"


async def test_scanner_blocks_new_entries_after_a_sufficient_miscalibrated_history(tmp_path) -> None:
    snapshot = _market(
        "BTCUSDT", "67000", trend_4h=1, trend_1h=1, setup_15m=1,
        trigger_5m=1, aggressive_flow_imbalance="0.6", depth_imbalance="0.2",
        flow_persistence="0.8", oi_change_ratio="0.05", price_impact_bps="12",
    )

    class Market:
        async def snapshot(self, symbol: str): return snapshot

    store = AuditStore(tmp_path / "audit.sqlite3")
    plan = next(item.order_plan for item in build_demo_state().opportunities if item.order_plan is not None)
    for index in range(30):
        store.upsert_signal_record(SignalRecord(
            signal_id=f"calibration:{index}", symbol="BTCUSDT", plan=plan,
            generated_at=snapshot.observed_at, predicted_probability=Decimal("0.70"),
            signal_type="trend_continuation",
            outcome=SignalOutcome.STOP, settled_at=snapshot.observed_at,
        ))

    state = build_live_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT",), audit_store=store)
    await scanner.scan_once()

    analysis = state.opportunities[0].analysis
    assert analysis is not None
    assert analysis.calibration.status == "DEGRADED"
    assert analysis.is_tradeable is False


async def test_scanner_does_not_apply_a_failed_altcoin_history_to_a_trend_signal(tmp_path) -> None:
    snapshot = _market(
        "BTCUSDT", "67000", trend_4h=1, trend_1h=1, setup_15m=1,
        trigger_5m=1, aggressive_flow_imbalance="0.6", depth_imbalance="0.2",
        flow_persistence="0.8", oi_change_ratio="0.05", price_impact_bps="12",
    )

    class Market:
        async def snapshot(self, symbol: str): return snapshot

    store = AuditStore(tmp_path / "audit.sqlite3")
    plan = next(item.order_plan for item in build_demo_state().opportunities if item.order_plan is not None)
    for index in range(30):
        store.upsert_signal_record(SignalRecord(
            signal_id=f"alt-calibration:{index}", symbol="SOLUSDT", plan=plan,
            generated_at=snapshot.observed_at, predicted_probability=Decimal("0.70"),
            signal_type="volatility_expansion", outcome=SignalOutcome.STOP, settled_at=snapshot.observed_at,
        ))

    state = build_live_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT",), audit_store=store)
    await scanner.scan_once()

    analysis = state.opportunities[0].analysis
    assert analysis is not None
    assert analysis.calibration.status == "INSUFFICIENT"


async def test_scanner_does_not_apply_failed_long_history_to_a_short_signal(tmp_path) -> None:
    snapshot = _market(
        "BTCUSDT", "67000", trend_4h=-1, trend_1h=-1, setup_15m=-1,
        trigger_5m=-1, aggressive_flow_imbalance="-0.6", depth_imbalance="-0.2",
        flow_persistence="0.8", oi_change_ratio="-0.05", price_impact_bps="-12",
    )

    class Market:
        async def snapshot(self, symbol: str): return snapshot

    store = AuditStore(tmp_path / "audit.sqlite3")
    long_plan = next(item.order_plan for item in build_demo_state().opportunities if item.order_plan is not None)
    for index in range(30):
        store.upsert_signal_record(SignalRecord(
            signal_id=f"long-calibration:{index}", symbol="BTCUSDT", plan=long_plan,
            generated_at=snapshot.observed_at, predicted_probability=Decimal("0.70"),
            signal_type="trend_continuation", outcome=SignalOutcome.STOP, settled_at=snapshot.observed_at,
        ))

    state = build_live_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("BTCUSDT",), audit_store=store)
    await scanner.scan_once()

    analysis = state.opportunities[0].analysis
    assert analysis is not None
    assert analysis.calibration.status == "INSUFFICIENT"


async def test_scanner_does_not_apply_failed_btc_history_to_an_eth_signal(tmp_path) -> None:
    snapshot = _market(
        "ETHUSDT", "4200", trend_4h=1, trend_1h=1, setup_15m=1,
        trigger_5m=1, aggressive_flow_imbalance="0.6", depth_imbalance="0.2",
        flow_persistence="0.8", oi_change_ratio="0.05", price_impact_bps="12",
    )

    class Market:
        async def snapshot(self, symbol: str): return snapshot

    store = AuditStore(tmp_path / "audit.sqlite3")
    plan = next(item.order_plan for item in build_demo_state().opportunities if item.order_plan is not None)
    for index in range(30):
        store.upsert_signal_record(SignalRecord(
            signal_id=f"btc-only:{index}", symbol="BTCUSDT", plan=plan,
            generated_at=snapshot.observed_at, predicted_probability=Decimal("0.70"),
            signal_type="trend_continuation", outcome=SignalOutcome.STOP, settled_at=snapshot.observed_at,
        ))

    state = build_live_state()
    scanner = LiveMarketScanner(state=state, market=Market(), watchlist=("ETHUSDT",), audit_store=store)
    await scanner.scan_once()

    analysis = state.opportunities[0].analysis
    assert analysis is not None
    assert analysis.calibration.status == "INSUFFICIENT"


async def test_scanner_surfaces_public_onchain_wallet_roster_without_claiming_a_cex_order() -> None:
    class Market:
        async def snapshot(self, symbol: str):
            return _market(symbol, "67000", trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1)

    class WalletTracker:
        async def observe(self):
            return (OnchainWalletFlow(
                wallet="0xabc",
                label="链上高手",
                token_symbol="SOL",
                direction=Direction.LONG,
                notional_delta=Decimal("500000"),
                score=84,
                is_baseline=True,
            ),)

    state = build_live_state()
    scanner = LiveMarketScanner(
        state=state,
        market=Market(),
        watchlist=("BTCUSDT",),
        wallet_tracker=WalletTracker(),
    )

    await scanner.scan_once()

    candidate = next(item for item in state.smart_money if item.wallet == "0xabc")
    assert candidate.kind is SmartMoneyKind.ONCHAIN_CLUSTER
    assert candidate.symbol == "SOL"
    assert candidate.chain == "BSC · Binance Web3 公开钱包"

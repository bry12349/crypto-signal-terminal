from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from crypto_signal_terminal.domain.models import (
    CalibrationState,
    Direction,
    Evidence,
    LifecycleState,
    MarketSnapshot,
    Opportunity,
    SmartMoneyCandidate,
    SmartMoneyKind,
    SourceKind,
)
from crypto_signal_terminal.engines.altcoin import AltcoinEngine
from crypto_signal_terminal.engines.smart_money import SmartMoneyEngine
from crypto_signal_terminal.engines.trend import TrendEngine
from crypto_signal_terminal.engines.evidence_fusion import EvidenceFusion
from crypto_signal_terminal.engines.signal_ledger import SignalRecord, settle_signal
from crypto_signal_terminal.market.health import classify_market_error
from crypto_signal_terminal.storage import AuditStore


class MarketProvider(Protocol):
    async def snapshot(self, symbol: str) -> MarketSnapshot: ...


class WalletTracker(Protocol):
    async def observe(self) -> tuple[Any, ...]: ...


DEFAULT_WATCHLIST = (
    "BTCUSDT", "ETHUSDT",
)


def rank_opportunities(opportunities: list[Opportunity]) -> list[Opportunity]:
    """Rank executable edge before confidence-only observations."""
    state_priority = {
        LifecycleState.ENTRY_VALID: 3,
        LifecycleState.TRIGGERED: 2,
        LifecycleState.ARMED: 1,
    }

    def rank(item: Opportunity) -> tuple[int, int, int, Decimal, Decimal, int, int]:
        analysis = item.analysis
        actionable = bool(
            item.state is LifecycleState.ENTRY_VALID
            and item.order_plan is not None
            and analysis is not None
            and analysis.is_tradeable
        )
        return (
            int(actionable),
            int(bool(analysis and analysis.is_tradeable)),
            state_priority.get(item.state, 0),
            analysis.expected_value if analysis else Decimal("-1"),
            analysis.p_tp_before_sl if analysis else Decimal("0"),
            analysis.opportunity_score if analysis else 0,
            item.confidence,
        )

    return sorted(opportunities, key=rank, reverse=True)


def _forming_observation(snapshot: MarketSnapshot, *, calibration: CalibrationState | None = None) -> Opportunity:
    """Keep a healthy market visible without pretending it is tradeable."""
    trend_1h = int(snapshot.features.get("trend_1h", 0))
    flow = Decimal(str(snapshot.features.get("aggressive_flow_imbalance", "0")))
    def trend_label(value: object) -> str:
        sign = int(value)
        return "偏多" if sign > 0 else "偏空" if sign < 0 else "中性"

    structure = " · ".join((
        f"4h {trend_label(snapshot.features.get('trend_4h', 0))}",
        f"1h {trend_label(trend_1h)}",
        f"15m {trend_label(snapshot.features.get('setup_15m', 0))}",
        f"5m {trend_label(snapshot.features.get('trigger_5m', 0))}",
    ))
    oi = Decimal(str(snapshot.features.get("oi_change_ratio", "0")))
    slippage = Decimal(str(snapshot.features.get("slippage_bps_1000", "0")))
    funding = snapshot.funding_rate * Decimal("100")
    confidence = min(55, 30 + int(abs(flow) * 30) + (8 if trend_1h else 0))
    direction = Direction.LONG if trend_1h >= 0 else Direction.SHORT
    analysis = EvidenceFusion().evaluate(
        snapshot,
        direction=direction,
        reward_to_risk=Decimal("1"),
        signal_type="market_observation",
        calibration=calibration,
    )
    return Opportunity(
        id=f"observe:{snapshot.symbol}",
        symbol=snapshot.symbol,
        source=SourceKind.NATIVE,
        state=LifecycleState.FORMING,
        confidence=confidence,
        created_at=snapshot.observed_at,
        updated_at=snapshot.observed_at,
        evidence=(
            Evidence(code="market_health", text="公开行情、盘口与成交数据健康", weight=12),
            Evidence(
                code="market_structure",
                text=f"{structure}",
                weight=10,
                value=flow,
            ),
            Evidence(
                code="derivatives_live",
                text=f"OI {oi * Decimal('100'):+.2f}% · 资金费率 {funding:+.4f}% · $1k 滑点 {slippage:.2f} bps",
                weight=8,
                value=oi,
            ),
        ),
        data_health=snapshot.data_health,
        title="实时市场观察 · 等待触发",
        risk="当前不具备可执行条件，系统不会生成订单建议",
        analysis=analysis,
    )


class LiveMarketScanner:
    def __init__(
        self,
        *,
        state: Any,
        market: MarketProvider,
        watchlist: tuple[str, ...] = DEFAULT_WATCHLIST,
        universe: Any | None = None,
        interval_seconds: float = 5,
        max_concurrency: int = 6,
        audit_store: AuditStore | None = None,
        wallet_tracker: WalletTracker | None = None,
    ) -> None:
        self.state = state
        self.market = market
        self.watchlist = watchlist
        self.universe = universe
        self.interval_seconds = interval_seconds
        self.max_concurrency = max(1, max_concurrency)
        self.audit_store = audit_store
        self.wallet_tracker = wallet_tracker
        self._wallet_roster: list[SmartMoneyCandidate] = []
        self._active_strategy_ids: set[str] = set()
        self.trend = TrendEngine()
        self.altcoin = AltcoinEngine()
        self.smart = SmartMoneyEngine()
        self.state.market_health_registry.set_watchlist(watchlist)

    def _calibration_state(self, signal_type: str, direction: Direction | None = None) -> CalibrationState:
        if self.audit_store is None:
            return CalibrationState(settled=0, mean_predicted=Decimal("0"), observed_win_rate=Decimal("0"), absolute_error=Decimal("0"), status="INSUFFICIENT")
        return CalibrationState.model_validate(self.audit_store.calibration_state(signal_type=signal_type, direction=direction))

    def _settle_recorded_signals(self, snapshots: list[MarketSnapshot]) -> None:
        if self.audit_store is None:
            return
        by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
        for record in self.audit_store.signal_records():
            snapshot = by_symbol.get(record.symbol)
            if snapshot is None:
                continue
            settled = settle_signal(record, snapshot.candles, now=snapshot.observed_at)
            if settled != record:
                self.audit_store.upsert_signal_record(settled)

    def _record_new_signals(self, opportunities: list[Opportunity]) -> None:
        if self.audit_store is None:
            return
        active = {
            opportunity.id
            for opportunity in opportunities
            if opportunity.state is LifecycleState.ENTRY_VALID and opportunity.order_plan is not None
        }
        for opportunity in opportunities:
            if opportunity.id not in active or opportunity.id in self._active_strategy_ids:
                continue
            record = SignalRecord(
                signal_id=f"{opportunity.id}:{int(opportunity.created_at.timestamp())}",
                symbol=opportunity.symbol,
                plan=opportunity.order_plan,
                generated_at=opportunity.created_at,
                predicted_probability=opportunity.analysis.p_tp_before_sl if opportunity.analysis else None,
                expected_value=opportunity.analysis.expected_value if opportunity.analysis else None,
                market_regime=opportunity.analysis.market_regime if opportunity.analysis else None,
                signal_type=opportunity.analysis.signal_type if opportunity.analysis else None,
            )
            self.audit_store.upsert_signal_record(record)
        self._active_strategy_ids = active

    @staticmethod
    def _wallet_candidates(flows: tuple[Any, ...], observed_at: datetime) -> list[SmartMoneyCandidate]:
        candidates: list[SmartMoneyCandidate] = []
        for flow in flows:
            action = "纳入追踪池" if flow.is_baseline else "出现新的链上活动"
            direction_text = "买入偏向" if flow.direction is Direction.LONG else "卖出偏向"
            candidates.append(SmartMoneyCandidate(
                id=f"onchain-wallet:{flow.wallet}:{int(observed_at.timestamp())}",
                symbol=flow.token_symbol,
                kind=SmartMoneyKind.ONCHAIN_CLUSTER,
                direction=flow.direction,
                score=flow.score,
                observed_at=observed_at,
                wallet=flow.wallet,
                chain="BSC · Binance Web3 公开钱包",
                token_address=flow.token_address,
                evidence=(
                    Evidence(
                        code="public_wallet_tracking",
                        text=f"{flow.label} {action}，当前{direction_text}",
                        weight=18 if not flow.is_baseline else 8,
                        value=flow.notional_delta,
                        source="binance_web3_public_wallet",
                    ),
                    Evidence(
                        code="public_wallet_scope",
                        text="公开链上地址排行榜；不是 Binance CEX 账户或其充值地址的归因",
                        weight=0,
                        source="binance_web3_public_wallet",
                    ),
                ),
            ))
        return candidates

    async def _current_wallet_roster(self, observed_at: datetime) -> list[SmartMoneyCandidate]:
        if self.wallet_tracker is None:
            return self._wallet_roster
        try:
            flows = await self.wallet_tracker.observe()
            # An empty result during the tracker's rate-limit/cache window
            # means "no new event", not "all tracked wallets disappeared".
            if flows:
                self._wallet_roster = self._wallet_candidates(flows, observed_at)
        except Exception:
            # Retain the last verified roster when the optional public source
            # is temporarily unavailable.
            pass
        return self._wallet_roster

    async def scan_once(self) -> int:
        if self.universe is not None:
            try:
                altcoins = await self.universe.top_altcoins()
                if altcoins:
                    self.watchlist = DEFAULT_WATCHLIST + tuple(item for item in altcoins if item not in DEFAULT_WATCHLIST)[:10]
                    self.state.market_health_registry.set_watchlist(self.watchlist)
            except Exception:
                # Retain the last successful universe instead of fabricating a static hot list.
                pass
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def fetch(symbol: str):
            async with semaphore:
                try:
                    return symbol, await self.market.snapshot(symbol), None
                except Exception as exc:
                    return symbol, None, classify_market_error(exc)

        results = await asyncio.gather(*(fetch(symbol) for symbol in self.watchlist))
        snapshots = []
        for symbol, snapshot, error in results:
            if snapshot is None:
                self.state.market_health_registry.record_failure(
                    symbol, observed_at=datetime.now(tz=UTC), reason=error or "unknown",
                )
            else:
                snapshots.append(snapshot)
                self.state.market_health_registry.record_success(snapshot)
        if not snapshots:
            wallet_candidates = await self._current_wallet_roster(datetime.now(tz=UTC))
            self.state.opportunities = []
            self.state.smart_money = sorted(wallet_candidates, key=lambda item: item.score, reverse=True)
            self.state.market_candles = {}
            self.state.market_health = self.state.market_health_registry.overall
            self.state.mode = "live"
            self.state.publish({"type": "snapshot", "payload": self.state.snapshot()})
            return 0
        self._settle_recorded_signals(snapshots)
        opportunities = []
        smart_money = []
        for snapshot in snapshots:
            self.state.market_candles[snapshot.symbol] = [item.model_dump(mode="json") for item in snapshot.candles]
            if snapshot.symbol in {"BTCUSDT", "ETHUSDT"}:
                opportunity = self.trend.evaluate(snapshot, calibration_for_direction=lambda direction: self._calibration_state("trend_continuation", direction))
            else:
                opportunity = self.altcoin.evaluate(snapshot, calibration_for_direction=lambda direction: self._calibration_state("volatility_expansion", direction))
            candidate = self.smart.evaluate_flow(snapshot)
            if opportunity:
                opportunities.append(opportunity)
            else:
                opportunities.append(_forming_observation(snapshot, calibration=self._calibration_state("market_observation")))
            if candidate:
                smart_money.append(candidate)
        smart_money.extend(await self._current_wallet_roster(max(item.observed_at for item in snapshots)))
        self.state.opportunities = rank_opportunities(opportunities)
        self._record_new_signals(self.state.opportunities)
        self.state.smart_money = sorted(smart_money, key=lambda item: item.score, reverse=True)
        self.state.market_health = self.state.market_health_registry.overall
        self.state.mode = "live"
        self.state.publish({"type": "snapshot", "payload": self.state.snapshot()})
        return len(snapshots)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.scan_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

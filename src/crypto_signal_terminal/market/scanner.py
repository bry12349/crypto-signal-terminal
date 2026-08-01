from __future__ import annotations

import asyncio
from typing import Any

from crypto_signal_terminal.engines.altcoin import AltcoinEngine
from crypto_signal_terminal.engines.smart_money import SmartMoneyEngine
from crypto_signal_terminal.engines.trend import TrendEngine
from crypto_signal_terminal.telegram.coordinator import MarketProvider


DEFAULT_WATCHLIST = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "SUIUSDT",
    "BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "AAVEUSDT", "LTCUSDT",
)


class LiveMarketScanner:
    def __init__(
        self,
        *,
        state: Any,
        market: MarketProvider,
        watchlist: tuple[str, ...] = DEFAULT_WATCHLIST,
        interval_seconds: float = 20,
    ) -> None:
        self.state = state
        self.market = market
        self.watchlist = watchlist
        self.interval_seconds = interval_seconds
        self.trend = TrendEngine()
        self.altcoin = AltcoinEngine()
        self.smart = SmartMoneyEngine()

    async def scan_once(self) -> int:
        semaphore = asyncio.Semaphore(3)

        async def fetch(symbol: str):
            async with semaphore:
                try:
                    return await self.market.snapshot(symbol)
                except Exception:
                    return None

        snapshots = [item for item in await asyncio.gather(*(fetch(symbol) for symbol in self.watchlist)) if item is not None]
        if not snapshots:
            self.state.market_health = "degraded"
            return 0
        opportunities = []
        smart_money = []
        for snapshot in snapshots:
            opportunity = self.trend.evaluate(snapshot) if snapshot.symbol in {"BTCUSDT", "ETHUSDT"} else self.altcoin.evaluate(snapshot)
            candidate = self.smart.evaluate_flow(snapshot)
            if opportunity:
                opportunities.append(opportunity)
            if candidate:
                smart_money.append(candidate)
        self.state.opportunities = sorted(opportunities, key=lambda item: item.confidence, reverse=True)
        self.state.smart_money = sorted(smart_money, key=lambda item: item.score, reverse=True)
        self.state.confirmations = [
            item for item in self.state.confirmations if item.signal.account_id != "demo"
        ]
        self.state.market_health = "healthy"
        self.state.mode = "live"
        try:
            self.state.event_queue.put_nowait({"type": "snapshot", "payload": self.state.snapshot()})
        except asyncio.QueueFull:
            pass
        return len(snapshots)

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.scan_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

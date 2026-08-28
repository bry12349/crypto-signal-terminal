"""Public BSC DEX OHLCV source for wallet-token market context."""

from __future__ import annotations

import time
from decimal import Decimal

import httpx

from crypto_signal_terminal.domain.models import Candle


class GeckoTerminalMarketClient:
    """Resolve a BSC token to its top public pool and read real OHLCV data."""

    _HEADERS = {"accept": "application/json;version=20230203"}
    _INTERVALS = {"5": ("minute", 5), "15": ("minute", 15), "60": ("hour", 1), "240": ("hour", 4)}

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(base_url="https://api.geckoterminal.com/api/v2", timeout=httpx.Timeout(10, connect=3))
        self._cache: dict[tuple[str, str], tuple[float, tuple[Candle, ...]]] = {}

    async def candles(self, token_address: str, interval: str, limit: int = 300) -> tuple[Candle, ...]:
        if interval not in self._INTERVALS or not token_address.startswith("0x"):
            raise ValueError("unsupported on-chain candle request")
        key = (token_address.lower(), interval)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < 55:
            return cached[1]
        pools = await self.client.get(f"/networks/bsc/tokens/{key[0]}/pools", headers=self._HEADERS)
        pools.raise_for_status()
        rows = pools.json().get("data") or []
        pool = next((item.get("attributes", {}).get("address") for item in rows if isinstance(item, dict) and item.get("attributes", {}).get("address")), None)
        if not pool:
            return ()
        timeframe, aggregate = self._INTERVALS[interval]
        response = await self.client.get(f"/networks/bsc/pools/{pool}/ohlcv/{timeframe}", params={"aggregate": aggregate, "limit": max(50, min(limit, 300)), "currency": "usd"}, headers=self._HEADERS)
        response.raise_for_status()
        values = response.json().get("data", {}).get("attributes", {}).get("ohlcv_list") or []
        candles = tuple(
            Candle(timestamp=int(row[0]), open=Decimal(str(row[1])), high=Decimal(str(row[2])), low=Decimal(str(row[3])), close=Decimal(str(row[4])), volume=Decimal(str(row[5])))
            for row in reversed(values) if isinstance(row, list) and len(row) >= 6 and Decimal(str(row[4])) > 0
        )
        self._cache[key] = (time.monotonic(), candles)
        return candles

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

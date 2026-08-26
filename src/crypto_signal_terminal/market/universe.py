from __future__ import annotations

import asyncio
from collections import defaultdict
from decimal import Decimal

import httpx


CORE_SYMBOLS = ("BTCUSDT", "ETHUSDT")


def _number(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


class MajorExchangeHotUniverse:
    """Top ten USDT perpetual altcoins, ranked by cross-exchange 24h turnover rank.

    Values from each venue use different units.  Per-venue rank rather than raw
    volume makes the aggregation comparable and requires broad market interest.
    """

    def __init__(self, *, client: httpx.AsyncClient | None = None, refresh_seconds: int = 300) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2))
        self.refresh_seconds = refresh_seconds
        self._cached: tuple[str, ...] = ()
        self._next_refresh = 0.0

    async def _get(self, url: str, **params: object) -> object:
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _rank(rows: list[tuple[str, Decimal]]) -> dict[str, int]:
        ranked: dict[str, int] = {}
        for index, (symbol, volume) in enumerate(sorted(rows, key=lambda item: item[1], reverse=True), start=1):
            if symbol.endswith("USDT") and symbol not in CORE_SYMBOLS and volume > 0:
                ranked[symbol] = index
        return ranked

    async def _sources(self) -> tuple[dict[str, int], ...]:
        bybit, binance, okx, bitget = await asyncio.gather(
            self._get("https://api.bybit.com/v5/market/tickers", category="linear"),
            self._get("https://fapi.binance.com/fapi/v1/ticker/24hr"),
            self._get("https://www.okx.com/api/v5/market/tickers", instType="SWAP"),
            self._get("https://api.bitget.com/api/v2/mix/market/tickers", productType="USDT-FUTURES"),
            return_exceptions=True,
        )
        results: list[dict[str, int]] = []
        if not isinstance(bybit, Exception):
            results.append(self._rank([(str(item.get("symbol", "")), _number(item.get("turnover24h"))) for item in bybit.get("result", {}).get("list", [])]))
        if not isinstance(binance, Exception):
            results.append(self._rank([(str(item.get("symbol", "")), _number(item.get("quoteVolume"))) for item in binance if isinstance(item, dict)]))
        if not isinstance(okx, Exception):
            results.append(self._rank([(str(item.get("instId", "")).replace("-", "").replace("SWAP", ""), _number(item.get("volCcy24h"))) for item in okx.get("data", [])]))
        if not isinstance(bitget, Exception):
            results.append(self._rank([(str(item.get("symbol", "")), _number(item.get("usdtVolume") or item.get("quoteVolume"))) for item in bitget.get("data", [])]))
        return tuple(results)

    async def top_altcoins(self) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        if self._cached and loop.time() < self._next_refresh:
            return self._cached
        sources = await self._sources()
        score: dict[str, Decimal] = defaultdict(Decimal)
        appearances: dict[str, int] = defaultdict(int)
        for ranks in sources:
            for symbol, rank in ranks.items():
                if rank <= 100:
                    score[symbol] += Decimal(101 - rank)
                    appearances[symbol] += 1
        if score:
            self._cached = tuple(symbol for symbol, _ in sorted(score.items(), key=lambda item: (appearances[item[0]], item[1]), reverse=True)[:10])
            self._next_refresh = loop.time() + self.refresh_seconds
        return self._cached

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

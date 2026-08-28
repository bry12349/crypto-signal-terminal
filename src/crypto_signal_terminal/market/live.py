from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from crypto_signal_terminal.domain.models import Candle, DataHealth, MarketSnapshot


def _d(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _sign(value: Decimal, threshold: Decimal = Decimal("0")) -> int:
    return 1 if value > threshold else -1 if value < -threshold else 0


def _book_slippage_bps(book: dict, reference: Decimal, notional_usd: Decimal = Decimal("1000")) -> Decimal:
    if reference <= 0:
        return Decimal("9999")
    required = notional_usd / reference
    results: list[Decimal] = []
    for side in (book.get("a", []), book.get("b", [])):
        remaining = required
        cost = Decimal("0")
        filled = Decimal("0")
        for row in side:
            quantity = min(remaining, _d(row[1]))
            cost += quantity * _d(row[0])
            filled += quantity
            remaining -= quantity
            if remaining <= 0:
                break
        if remaining > 0 or filled <= 0:
            return Decimal("9999")
        average = cost / filled
        results.append(abs(average - reference) / reference * Decimal("10000"))
    return max(results, default=Decimal("9999"))


class BybitCompositeMarketClient:
    """Builds a confirmation snapshot from public derivatives data only."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        binance_client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        include_peers: bool = True,
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url="https://api.bybit.com",
            timeout=httpx.Timeout(4, connect=2),
            limits=httpx.Limits(max_connections=24, max_keepalive_connections=12),
        )
        self._owns_binance_client = binance_client is None
        self._binance_client = binance_client or httpx.AsyncClient(
            base_url="https://fapi.binance.com",
            timeout=httpx.Timeout(4, connect=2),
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
        )
        self._peer_client = httpx.AsyncClient(
            base_url="https://www.okx.com",
            timeout=httpx.Timeout(2, connect=1),
            limits=httpx.Limits(max_connections=12, max_keepalive_connections=6),
        )
        self.clock = clock
        self.include_peers = include_peers

    async def _get(self, client: httpx.AsyncClient, path: str, **params: object) -> tuple[dict, int | None]:
        response = await client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("retCode") != 0:
            raise RuntimeError(f"bybit_error:{payload.get('retCode')}")
        return payload["result"], int(payload["time"]) if payload.get("time") else None

    async def snapshot(self, symbol: str) -> MarketSnapshot:
        normalized = symbol.upper().replace("/", "").replace("-", "")
        client = self.client
        started = self.clock()
        try:
            responses = await asyncio.gather(
                self._get(client, "/v5/market/tickers", category="linear", symbol=normalized),
                self._get(client, "/v5/market/kline", category="linear", symbol=normalized, interval="240", limit=24),
                self._get(client, "/v5/market/kline", category="linear", symbol=normalized, interval="60", limit=24),
                self._get(client, "/v5/market/kline", category="linear", symbol=normalized, interval="15", limit=24),
                self._get(client, "/v5/market/kline", category="linear", symbol=normalized, interval="5", limit=300),
                self._get(client, "/v5/market/orderbook", category="linear", symbol=normalized, limit=50),
                self._get(client, "/v5/market/recent-trade", category="linear", symbol=normalized, limit=200),
                self._get(client, "/v5/market/open-interest", category="linear", symbol=normalized, intervalTime="5min", limit=2),
            )
            (ticker, ticker_time), (candles_4h, _), (candles_1h, _), (candles_15m, _), (candles_5m, _), (book, _), (trades, _), (oi, _) = responses
            received_at = self.clock()
            observed = datetime.fromtimestamp(ticker_time / 1000, tz=UTC) if ticker_time else received_at
            ticker_item = ticker["list"][0]
            features = self._features(candles_4h["list"], candles_1h["list"], candles_15m["list"], candles_5m["list"], book, trades["list"], oi["list"])
            candle_rows = tuple(
                Candle(
                    timestamp=int(row[0]) // 1000,
                    open=_d(row[1]), high=_d(row[2]), low=_d(row[3]), close=_d(row[4]), volume=_d(row[5]),
                )
                for row in reversed(candles_5m["list"])
            )
            price = _d(ticker_item["lastPrice"])
            latency_ms = max(0, int((received_at - started).total_seconds() * 1000))
            source_age_ms = max(0, int((received_at - observed).total_seconds() * 1000))
            healthy = latency_ms <= 5000 and source_age_ms <= 10000
            peer_confirmations = 1 + (await self._okx_price_confirms(normalized, price) if self.include_peers else 0)
            return MarketSnapshot(
                symbol=normalized,
                exchange="bybit-public-composite",
                observed_at=observed,
                price=price,
                bid=_d(ticker_item["bid1Price"]),
                ask=_d(ticker_item["ask1Price"]),
                open_interest=_d(ticker_item.get("openInterest")),
                funding_rate=_d(ticker_item.get("fundingRate")),
                volume_24h=_d(ticker_item.get("turnover24h")),
                data_health=DataHealth(
                    healthy=healthy,
                    observed_at=observed,
                    latency_ms=latency_ms,
                    stale_sources=() if healthy else ("bybit_ticker",),
                    reason=None if healthy else "exchange timestamp or request latency exceeded limit",
                ),
                peer_confirmations=peer_confirmations,
                features=features,
                candles=candle_rows,
            )
        except Exception:
            return await self._binance_snapshot(normalized, started)
        finally:
            pass

    async def _binance_snapshot(self, symbol: str, started: datetime) -> MarketSnapshot:
        client = self._binance_client
        ticker, four, hour, fifteen, five, book, trades, oi, oi_history = await asyncio.gather(
            client.get("/fapi/v1/ticker/24hr", params={"symbol": symbol}),
            client.get("/fapi/v1/klines", params={"symbol": symbol, "interval": "4h", "limit": 24}),
            client.get("/fapi/v1/klines", params={"symbol": symbol, "interval": "1h", "limit": 24}),
            client.get("/fapi/v1/klines", params={"symbol": symbol, "interval": "15m", "limit": 24}),
            client.get("/fapi/v1/klines", params={"symbol": symbol, "interval": "5m", "limit": 300}),
            client.get("/fapi/v1/depth", params={"symbol": symbol, "limit": 50}),
            client.get("/fapi/v1/aggTrades", params={"symbol": symbol, "limit": 200}),
            client.get("/fapi/v1/openInterest", params={"symbol": symbol}),
            client.get("/futures/data/openInterestHist", params={"symbol": symbol, "period": "5m", "limit": 2}),
        )
        for response in (ticker, four, hour, fifteen, five, book, trades, oi, oi_history): response.raise_for_status()
        ticker_item = ticker.json(); received_at = self.clock(); price = _d(ticker_item["lastPrice"])
        def rows(response: httpx.Response) -> list: return response.json()
        def candle_rows(response: httpx.Response) -> list: return [[item[0], item[1], item[2], item[3], item[4], item[5]] for item in rows(response)]
        book_data = book.json(); trade_rows = [{"side": "Sell" if item["m"] else "Buy", "size": item["q"], "price": item["p"]} for item in trades.json()]
        oi_value = oi.json()["openInterest"]
        # Binance returns historical OI in chronological order; feature fusion
        # expects the most recent value first, matching the Bybit response.
        oi_rows = [{"openInterest": item.get("sumOpenInterest", "0")} for item in reversed(oi_history.json())]
        features = self._features(candle_rows(four), candle_rows(hour), candle_rows(fifteen), candle_rows(five), {"b": book_data["bids"], "a": book_data["asks"]}, trade_rows, oi_rows)
        values = candle_rows(five)
        return MarketSnapshot(symbol=symbol, exchange="binance-public-composite", observed_at=received_at, price=price, bid=_d(ticker_item["bidPrice"]), ask=_d(ticker_item["askPrice"]), open_interest=_d(oi_value), funding_rate=_d(ticker_item.get("lastFundingRate")), volume_24h=_d(ticker_item.get("quoteVolume")), data_health=DataHealth(healthy=True, observed_at=received_at, latency_ms=max(0, int((received_at - started).total_seconds() * 1000))), peer_confirmations=1, features=features, candles=tuple(Candle(timestamp=int(row[0]) // 1000, open=_d(row[1]), high=_d(row[2]), low=_d(row[3]), close=_d(row[4]), volume=_d(row[5])) for row in values))

    async def candles(self, symbol: str, interval: str, limit: int = 300) -> tuple[Candle, ...]:
        normalized = symbol.upper().replace("/", "").replace("-", "")
        if interval not in {"5", "15", "60", "240"}:
            raise ValueError("unsupported candle interval")
        safe_limit = max(50, min(limit, 500))
        try:
            result, _ = await self._get(
                self.client, "/v5/market/kline", category="linear", symbol=normalized,
                interval=interval, limit=safe_limit,
            )
            rows = reversed(result["list"])
        except Exception:
            # The desktop chart must remain usable when a regional Bybit edge is
            # unavailable. Binance USD-M provides the same public perpetual OHLCV.
            binance_interval = {"5": "5m", "15": "15m", "60": "1h", "240": "4h"}[interval]
            response = await self._binance_client.get(
                "/fapi/v1/klines", params={"symbol": normalized, "interval": binance_interval, "limit": safe_limit},
            )
            response.raise_for_status()
            rows = response.json()
        return tuple(
            Candle(timestamp=int(row[0]) // 1000, open=_d(row[1]), high=_d(row[2]), low=_d(row[3]), close=_d(row[4]), volume=_d(row[5]))
            for row in rows
        )

    async def derivatives(self, symbol: str, interval: str, limit: int = 200) -> dict[str, list[dict[str, int | str]]]:
        """Return public, timestamped derivatives series for chart indicators."""
        normalized = symbol.upper().replace("/", "").replace("-", "")
        if interval not in {"5", "15", "60", "240"}:
            raise ValueError("unsupported derivatives interval")
        interval_time = {"5": "5min", "15": "5min", "60": "1h", "240": "4h"}[interval]
        safe_limit = max(20, min(limit, 200))
        oi, funding = await asyncio.gather(
            self._get(self.client, "/v5/market/open-interest", category="linear", symbol=normalized, intervalTime=interval_time, limit=safe_limit),
            self._get(self.client, "/v5/market/funding/history", category="linear", symbol=normalized, limit=safe_limit),
        )
        oi_rows = list(reversed(oi[0].get("list", [])))
        funding_rows = list(reversed(funding[0].get("list", [])))
        return {
            "open_interest": [
                {"time": int(row["timestamp"]) // 1000, "value": str(row["openInterest"])}
                for row in oi_rows if row.get("timestamp") is not None and row.get("openInterest") is not None
            ],
            "funding": [
                {"time": int(row["fundingRateTimestamp"]) // 1000, "value": str(row["fundingRate"])}
                for row in funding_rows if row.get("fundingRateTimestamp") is not None and row.get("fundingRate") is not None
            ],
        }

    async def _okx_price_confirms(self, symbol: str, reference: Decimal) -> int:
        if not symbol.endswith("USDT") or reference <= 0:
            return 0
        instrument = f"{symbol[:-4]}-USDT-SWAP"
        try:
            response = await self._peer_client.get("/api/v5/market/ticker", params={"instId": instrument})
            response.raise_for_status()
            item = response.json()["data"][0]
            peer_mid = (_d(item["bidPx"]) + _d(item["askPx"])) / 2
            deviation = abs(peer_mid - reference) / reference
            return 1 if deviation <= Decimal("0.0075") else 0
        except Exception:
            return 0

    async def close(self) -> None:
        await self._peer_client.aclose()
        if self._owns_client:
            await self.client.aclose()
        if self._owns_binance_client:
            await self._binance_client.aclose()

    @staticmethod
    def _features(candles_4h: list, candles_1h: list, candles_15m: list, candles_5m: list, book: dict, trades: list[dict], oi_rows: list[dict]) -> dict[str, str | int]:
        four = list(reversed(candles_4h))[:-1]
        hour = list(reversed(candles_1h))[:-1]
        fifteen = list(reversed(candles_15m))[:-1]
        five = list(reversed(candles_5m))[:-1]
        four_closes = [_d(row[4]) for row in four]
        hour_closes = [_d(row[4]) for row in hour]
        fifteen_closes = [_d(row[4]) for row in fifteen]
        five_closes = [_d(row[4]) for row in five]
        hour_move = hour_closes[-1] - hour_closes[-2] if len(hour_closes) >= 2 else Decimal("0")
        four_hour_move = four_closes[-1] - four_closes[-2] if len(four_closes) >= 2 else Decimal("0")
        setup_move = fifteen_closes[-1] - fifteen_closes[-2] if len(fifteen_closes) >= 2 else Decimal("0")
        trigger_move = five_closes[-1] - five_closes[-2] if len(five_closes) >= 2 else Decimal("0")

        bids = sum((_d(row[1]) for row in book.get("b", [])), Decimal("0"))
        asks = sum((_d(row[1]) for row in book.get("a", [])), Decimal("0"))
        depth = (bids - asks) / (bids + asks) if bids + asks else Decimal("0")

        buys = sum((_d(item["size"]) for item in trades if item.get("side") == "Buy"), Decimal("0"))
        sells = sum((_d(item["size"]) for item in trades if item.get("side") == "Sell"), Decimal("0"))
        flow = (buys - sells) / (buys + sells) if buys + sells else Decimal("0")

        chunk_signs: list[int] = []
        chunk_size = max(1, len(trades) // 4)
        for start in range(0, len(trades), chunk_size):
            chunk = trades[start:start + chunk_size]
            chunk_buy = sum((_d(item["size"]) for item in chunk if item.get("side") == "Buy"), Decimal("0"))
            chunk_sell = sum((_d(item["size"]) for item in chunk if item.get("side") == "Sell"), Decimal("0"))
            chunk_signs.append(_sign(chunk_buy - chunk_sell))
        desired = _sign(flow)
        persistence = Decimal(sum(1 for item in chunk_signs if item == desired)) / Decimal(len(chunk_signs) or 1)

        notionals = sorted(_d(item["size"]) * _d(item["price"]) for item in trades)
        baseline_notional = notionals[max(0, int(len(notionals) * 0.1) - 1)] if notionals else Decimal("0")
        threshold = max(Decimal("100000"), baseline_notional * Decimal("8"))
        large_count = sum(1 for notional in notionals if notional >= threshold)

        oi_values = [_d(item.get("openInterest")) for item in oi_rows]
        oi_ratio = oi_values[0] / oi_values[-1] - 1 if len(oi_values) >= 2 and oi_values[-1] else Decimal("0")

        ranges = [_d(row[2]) - _d(row[3]) for row in five]
        current_range = ranges[-1] if ranges else Decimal("0")
        atr_percentile = Decimal(sum(1 for item in ranges if item <= current_range)) / Decimal(len(ranges) or 1) * 100
        volumes = [_d(row[5]) for row in five]
        baseline = sum(volumes[-13:-1], Decimal("0")) / Decimal(len(volumes[-13:-1]) or 1)
        volume_acceleration = volumes[-1] / baseline if volumes and baseline else Decimal("1")

        first_price = _d(trades[-1]["price"]) if trades else Decimal("0")
        last_price = _d(trades[0]["price"]) if trades else Decimal("0")
        impact = (last_price - first_price) / first_price * 10000 if first_price else Decimal("0")
        absorption = abs(flow) - min(Decimal("1"), abs(impact) / Decimal("20"))
        return {
            "trend_4h": _sign(four_hour_move),
            "trend_1h": _sign(hour_move),
            "setup_15m": _sign(setup_move),
            "trigger_5m": _sign(trigger_move),
            "depth_imbalance": str(depth.quantize(Decimal("0.0001"))),
            "aggressive_flow_imbalance": str(flow.quantize(Decimal("0.0001"))),
            "flow_persistence": str(persistence.quantize(Decimal("0.01"))),
            "large_trade_count": large_count,
            "large_trade_threshold_usd": str(threshold.quantize(Decimal("0.01"))),
            "slippage_bps_1000": str(_book_slippage_bps(book, five_closes[-1] if five_closes else Decimal("0")).quantize(Decimal("0.01"))),
            "oi_change_ratio": str(oi_ratio.quantize(Decimal("0.0001"))),
            "atr_percentile": str(atr_percentile.quantize(Decimal("0.1"))),
            "volume_acceleration": str(volume_acceleration.quantize(Decimal("0.01"))),
            "price_impact_bps": str(impact.quantize(Decimal("0.01"))),
            "absorption": str(absorption.quantize(Decimal("0.01"))),
        }

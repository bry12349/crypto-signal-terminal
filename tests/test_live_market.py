from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from crypto_signal_terminal.market.live import BybitCompositeMarketClient


def _response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/tickers"):
        result = {"list": [{"lastPrice": "100", "bid1Price": "99.9", "ask1Price": "100.1", "openInterest": "1100", "fundingRate": "0.0001", "turnover24h": "50000000"}]}
    elif path.endswith("/kline"):
        interval = request.url.params["interval"]
        rows = []
        for index in range(24):
            close = 100 - index if interval == "60" else 100 - index * 0.1
            volume = 40 if index == 0 else 10
            rows.append([str(1_700_000_000_000 - index * 300_000), str(close - 0.2), str(close + 0.4), str(close - 0.4), str(close), str(volume), "1000"])
        result = {"list": rows}
    elif path.endswith("/orderbook"):
        result = {"b": [["99.95", "80"]], "a": [["100.04", "20"]]}
    elif path.endswith("/recent-trade"):
        result = {"list": [{"side": "Buy", "size": "2000", "price": "100"}] * 8 + [{"side": "Sell", "size": "1", "price": "99.9"}] * 2}
    elif path.endswith("/open-interest"):
        result = {"list": [{"openInterest": "1100", "timestamp": "1700000300000"}, {"openInterest": "1000", "timestamp": "1700000000000"}]}
    elif path.endswith("/funding/history"):
        result = {"list": [{"fundingRate": "0.0001", "fundingRateTimestamp": "1700000000000"}]}
    else:
        raise AssertionError(path)
    return httpx.Response(200, json={"retCode": 0, "result": result}, request=request)


@pytest.mark.asyncio
async def test_live_market_snapshot_derives_flow_trend_depth_and_oi() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_response), base_url="https://api.bybit.com") as http:
        snapshot = await BybitCompositeMarketClient(client=http, clock=lambda: datetime(2026, 8, 1, tzinfo=UTC), include_peers=False).snapshot("solusdt")
    assert snapshot.symbol == "SOLUSDT"
    assert snapshot.price == 100
    assert snapshot.features["trend_1h"] == 1
    assert Decimal(str(snapshot.features["depth_imbalance"])) > 0
    assert Decimal(str(snapshot.features["aggressive_flow_imbalance"])) > Decimal("0.5")
    assert Decimal(str(snapshot.features["oi_change_ratio"])) == Decimal("0.1")
    assert snapshot.features["large_trade_count"] == 8
    assert Decimal(str(snapshot.features["slippage_bps_1000"])) <= Decimal("15")
    assert snapshot.data_health.healthy is True
    assert len(snapshot.candles) == 24
    assert snapshot.candles[-1].close == Decimal("100")


@pytest.mark.asyncio
async def test_exchange_timestamp_marks_old_market_data_unhealthy() -> None:
    def stale_response(request: httpx.Request) -> httpx.Response:
        response = _response(request)
        payload = response.json()
        payload["time"] = 1_700_000_000_000
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(stale_response), base_url="https://api.bybit.com") as http:
        snapshot = await BybitCompositeMarketClient(
            client=http,
            clock=lambda: datetime(2026, 8, 1, tzinfo=UTC),
            include_peers=False,
        ).snapshot("SOLUSDT")
    assert snapshot.data_health.healthy is False
    assert snapshot.data_health.stale_sources == ("bybit_ticker",)


@pytest.mark.asyncio
async def test_candles_falls_back_to_binance_when_bybit_kline_is_unavailable() -> None:
    def bybit_unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    def binance_kline(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/klines"
        assert request.url.params["interval"] == "1h"
        return httpx.Response(200, json=[
            ["1700000000000", "100", "102", "99", "101", "42"],
            ["1700003600000", "101", "103", "100", "102", "51"],
        ], request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(bybit_unavailable), base_url="https://api.bybit.com") as bybit, httpx.AsyncClient(transport=httpx.MockTransport(binance_kline), base_url="https://fapi.binance.com") as binance:
        client = BybitCompositeMarketClient(client=bybit, binance_client=binance, include_peers=False)
        candles = await client.candles("BTCUSDT", "60", limit=300)
    assert [candle.close for candle in candles] == [Decimal("101"), Decimal("102")]
    assert candles[-1].timestamp - candles[0].timestamp == 3600


@pytest.mark.asyncio
async def test_live_market_exposes_timestamped_open_interest_and_funding_history() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_response), base_url="https://api.bybit.com") as http:
        client = BybitCompositeMarketClient(client=http, include_peers=False)
        history = await client.derivatives("BTCUSDT", "5", limit=50)
    assert history["open_interest"][-1]["value"] == "1100"
    assert history["funding"][-1]["value"] == "0.0001"


@pytest.mark.asyncio
async def test_snapshot_falls_back_to_binance_when_bybit_composite_times_out() -> None:
    def unavailable(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    def binance(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("ticker/24hr"):
            return httpx.Response(200, json={"lastPrice": "100", "bidPrice": "99.9", "askPrice": "100.1", "openInterest": "1100", "lastFundingRate": "0.0001", "quoteVolume": "50000000"}, request=request)
        if path.endswith("klines"):
            rows = [[str(1_700_000_000_000 + index * 300_000), "99", "101", "98", "100", "42"] for index in range(24)]
            return httpx.Response(200, json=rows, request=request)
        if path.endswith("depth"):
            return httpx.Response(200, json={"bids": [["99.95", "80"]], "asks": [["100.04", "20"]]}, request=request)
        if path.endswith("aggTrades"):
            return httpx.Response(200, json=[{"m": False, "q": "2000", "p": "100"}] * 10, request=request)
        if path.endswith("openInterest"):
            return httpx.Response(200, json={"openInterest": "1100"}, request=request)
        if path.endswith("openInterestHist"):
            return httpx.Response(200, json=[{"sumOpenInterest": "1000"}, {"sumOpenInterest": "1100"}], request=request)
        raise AssertionError(path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(unavailable), base_url="https://api.bybit.com") as bybit, httpx.AsyncClient(transport=httpx.MockTransport(binance), base_url="https://fapi.binance.com") as futures:
        snapshot = await BybitCompositeMarketClient(client=bybit, binance_client=futures, include_peers=False).snapshot("BTCUSDT")
    assert snapshot.exchange == "binance-public-composite"
    assert snapshot.price == Decimal("100")
    assert Decimal(str(snapshot.features["oi_change_ratio"])) == Decimal("0.1")

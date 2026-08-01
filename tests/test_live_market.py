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
            rows.append([str(1000 - index), str(close - 0.2), str(close + 0.4), str(close - 0.4), str(close), str(volume), "1000"])
        result = {"list": rows}
    elif path.endswith("/orderbook"):
        result = {"b": [["99.9", "80"]], "a": [["100.1", "20"]]}
    elif path.endswith("/recent-trade"):
        result = {"list": [{"side": "Buy", "size": "10", "price": "100"}] * 8 + [{"side": "Sell", "size": "1", "price": "99.9"}] * 2}
    elif path.endswith("/open-interest"):
        result = {"list": [{"openInterest": "1100"}, {"openInterest": "1000"}]}
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
    assert snapshot.data_health.healthy is True

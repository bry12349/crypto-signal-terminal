import httpx
import pytest

from crypto_signal_terminal.market.universe import MajorExchangeHotUniverse


@pytest.mark.asyncio
async def test_hot_universe_keeps_only_cross_exchange_top_ten_altcoin_perpetuals() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bybit" in str(request.url):
            payload = {"retCode": 0, "result": {"list": [{"symbol": f"A{i}USDT", "turnover24h": str(1000 - i)} for i in range(12)]}}
        elif "binance" in str(request.url):
            payload = [{"symbol": f"A{i}USDT", "quoteVolume": str(1200 - i)} for i in range(12)]
        elif "okx" in str(request.url):
            payload = {"data": [{"instId": f"A{i}-USDT-SWAP", "volCcy24h": str(900 - i)} for i in range(12)]}
        else:
            payload = {"code": "00000", "data": [{"symbol": f"A{i}USDT", "usdtVolume": str(800 - i)} for i in range(12)]}
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        universe = MajorExchangeHotUniverse(client=client)
        symbols = await universe.top_altcoins()

    assert len(symbols) == 10
    assert symbols[0] == "A0USDT"
    assert "BTCUSDT" not in symbols and "ETHUSDT" not in symbols

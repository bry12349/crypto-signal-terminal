import httpx
import pytest

from crypto_signal_terminal.adapters.geckoterminal import GeckoTerminalMarketClient


@pytest.mark.asyncio
async def test_geckoterminal_loads_bsc_token_candles_from_its_top_pool() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tokens/0xtoken/pools"):
            return httpx.Response(200, json={"data": [{"attributes": {"address": "0xpool"}}]})
        assert request.url.path.endswith("/pools/0xpool/ohlcv/hour")
        assert request.url.params["aggregate"] == "1"
        return httpx.Response(200, json={"data": {"attributes": {"ohlcv_list": [[1_700_003_600, 12, 14, 11, 13, 42], [1_700_000_000, 10, 13, 9, 12, 31]]}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.geckoterminal.com/api/v2") as client:
        market = GeckoTerminalMarketClient(client=client)
        candles = await market.candles("0xtoken", "60", limit=300)

    assert [item.timestamp for item in candles] == [1_700_000_000, 1_700_003_600]
    assert str(candles[-1].close) == "13"

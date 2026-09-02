from decimal import Decimal

import httpx
import pytest

from crypto_signal_terminal.adapters.binance_web3 import BinanceWeb3WalletTracker
from crypto_signal_terminal.domain.models import Direction


@pytest.mark.asyncio
async def test_web3_tracker_bootstraps_public_wallet_roster_then_emits_activity_delta() -> None:
    rows = [
        [{
            "address": "0xabc",
            "addressLabel": "链上高手",
            "tags": None,
            "realizedPnl": "120000",
            "winRate": "0.72",
            "totalVolume": "500000",
            "buyVolume": "320000",
            "sellVolume": "180000",
            "lastActivity": 1000,
            "topEarningTokens": [{"tokenAddress": "0xsol", "tokenSymbol": "SOL", "realizedPnl": "50000"}],
        }],
        [{
            "address": "0xabc",
            "addressLabel": "链上高手",
            "tags": None,
            "realizedPnl": "125000",
            "winRate": "0.72",
            "totalVolume": "530000",
            "buyVolume": "350000",
            "sellVolume": "180000",
            "lastActivity": 2000,
            "topEarningTokens": [{"tokenAddress": "0xsol", "tokenSymbol": "SOL", "realizedPnl": "50000"}],
        }],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/market/leaderboard/query/ai")
        return httpx.Response(200, json={"code": "000000", "data": {"data": rows.pop(0)}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://web3.binance.com") as client:
        tracker = BinanceWeb3WalletTracker(client=client, refresh_seconds=0)
        roster = await tracker.observe()
        activity = await tracker.observe()

    assert roster[0].is_baseline is True
    assert roster[0].wallet == "0xabc"
    assert roster[0].token_symbol == "SOL"
    assert roster[0].token_address == "0xsol"
    assert activity[0].is_baseline is False
    assert activity[0].notional_delta == Decimal("30000")
    assert activity[0].direction is Direction.LONG


@pytest.mark.asyncio
async def test_web3_tracker_preserves_unicode_token_ticker_instead_of_collapsing_to_onchain() -> None:
    row = {
        "address": "0xabc", "realizedPnl": "1", "winRate": "0.5", "totalVolume": "100",
        "buyVolume": "60", "sellVolume": "40", "lastActivity": 1,
        "topEarningTokens": [{"tokenAddress": "0xbeea1d", "tokenSymbol": "牛来"}],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "000000", "data": {"data": [row]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://web3.binance.com") as client:
        tracker = BinanceWeb3WalletTracker(client=client, refresh_seconds=0)
        flows = await tracker.observe()
    assert flows[0].token_symbol == "牛来"

"""Verified public on-chain wallet intelligence from Binance Web3.

This is intentionally separate from Binance Futures' old anonymous leaderboard:
the records here contain actual public blockchain addresses, not `encryptedUid`s.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal

import httpx

from crypto_signal_terminal.domain.models import Direction


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _symbol(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())[:20]


@dataclass(frozen=True)
class OnchainWalletFlow:
    wallet: str
    label: str
    token_symbol: str
    direction: Direction
    notional_delta: Decimal
    score: int
    is_baseline: bool
    token_address: str | None = None
    source: str = "binance_web3_public_wallet"


@dataclass(frozen=True)
class _WalletSnapshot:
    activity: int
    volume: Decimal
    buy_volume: Decimal
    sell_volume: Decimal
    label: str
    token_symbol: str
    score: int
    token_address: str | None = None


class BinanceWeb3WalletTracker:
    """Observe public BSC smart-money/KOL wallet leaderboard changes.

    A first successful poll produces a transparent tracking roster. Later polls
    emit only wallets whose reported activity or volume actually changed.
    """

    _HEADERS = {
        "accept-encoding": "identity",
        "user-agent": "binance-web3/3.0 (Crypto Signal Terminal)",
    }
    _PATH = "/bapi/defi/v1/public/wallet-direct/market/leaderboard/query/ai"

    def __init__(self, *, client: httpx.AsyncClient | None = None, refresh_seconds: int = 30, max_wallets: int = 20) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(base_url="https://web3.binance.com", timeout=httpx.Timeout(8, connect=3))
        self.refresh_seconds = max(0, refresh_seconds)
        self.max_wallets = max(1, min(25, max_wallets))
        self._wallets: dict[str, _WalletSnapshot] = {}
        self._next_refresh = 0.0

    @staticmethod
    def _score(row: dict) -> int:
        win_rate = _decimal(row.get("winRate"))
        pnl = _decimal(row.get("realizedPnl"))
        volume = _decimal(row.get("totalVolume"))
        tags = {str(tag).lower() for tag in (row.get("tags") or ())}
        return min(95, 50 + min(20, int(win_rate * 25)) + min(15, int(pnl / Decimal("10000"))) + min(10, int(volume / Decimal("100000"))) + (5 if "smart money" in tags or "kol" in tags else 0))

    @classmethod
    def _snapshot(cls, row: dict) -> _WalletSnapshot | None:
        address = str(row.get("address") or "").lower()
        if not address:
            return None
        tokens = row.get("topEarningTokens") or []
        token = tokens[0] if isinstance(tokens, list) and tokens and isinstance(tokens[0], dict) else {}
        token_symbol = _symbol(token.get("tokenSymbol")) if token else "ONCHAIN"
        token_symbol = token_symbol if len(token_symbol) >= 2 else "ONCHAIN"
        return _WalletSnapshot(
            activity=int(row.get("lastActivity") or 0),
            volume=_decimal(row.get("totalVolume")),
            buy_volume=_decimal(row.get("buyVolume")),
            sell_volume=_decimal(row.get("sellVolume")),
            label=str(row.get("addressLabel") or "公开链上地址"),
            token_symbol=token_symbol,
            token_address=str(token.get("tokenAddress") or "").lower() or None,
            score=cls._score(row),
        )

    async def observe(self) -> tuple[OnchainWalletFlow, ...]:
        loop = asyncio.get_running_loop()
        if loop.time() < self._next_refresh:
            return ()
        response = await self.client.get(
            self._PATH,
            params={"chainId": "56", "period": "7d", "tag": "ALL", "sortBy": 0, "orderBy": 0, "pageNo": 1, "pageSize": self.max_wallets},
            headers=self._HEADERS,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "000000":
            raise RuntimeError("binance_web3_leaderboard_rejected")
        data = payload.get("data") or {}
        rows = data.get("data", []) if isinstance(data, dict) else []
        next_wallets: dict[str, _WalletSnapshot] = {}
        flows: list[OnchainWalletFlow] = []
        baseline = not self._wallets
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            wallet = str(row.get("address") or "").lower()
            current = self._snapshot(row)
            if not wallet or current is None:
                continue
            next_wallets[wallet] = current
            previous = self._wallets.get(wallet)
            changed = previous is not None and (
                current.activity > previous.activity or current.volume != previous.volume
            )
            if not baseline and not changed:
                continue
            delta_buy = current.buy_volume - (previous.buy_volume if previous else Decimal("0"))
            delta_sell = current.sell_volume - (previous.sell_volume if previous else Decimal("0"))
            direction = Direction.LONG if delta_buy >= delta_sell else Direction.SHORT
            notional_delta = abs((current.volume - previous.volume) if previous else current.volume)
            flows.append(OnchainWalletFlow(
                wallet=wallet,
                label=current.label,
                token_symbol=current.token_symbol,
                token_address=current.token_address,
                direction=direction,
                notional_delta=notional_delta,
                score=current.score,
                is_baseline=baseline,
            ))
        self._wallets = next_wallets
        self._next_refresh = loop.time() + self.refresh_seconds
        return tuple(flows)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

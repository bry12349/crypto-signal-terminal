from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import AsyncIterator, Protocol, Sequence

import websockets

from crypto_signal_terminal.market.state import MarketEvent


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.upper().replace("-SWAP", "").replace(":USDT", "")
    return re.sub(r"[^A-Z0-9]", "", normalized)


def _time(ms: int | str) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, tz=UTC)


def _received(ms: int) -> datetime:
    return _time(ms)


def decode_binance_message(message: dict, *, received_ms: int) -> list[MarketEvent]:
    data = message.get("data", message)
    symbol = normalize_symbol(data.get("s", ""))
    event_time = _time(data.get("E", received_ms))
    common = {"exchange": "binance", "symbol": symbol, "exchange_time": event_time, "received_at": _received(received_ms)}
    kind = data.get("e")
    if kind == "bookTicker":
        return [MarketEvent(kind="book_snapshot", sequence=int(data["u"]), payload={"bid": Decimal(data["b"]), "bid_size": Decimal(data["B"]), "ask": Decimal(data["a"]), "ask_size": Decimal(data["A"])}, **common)]
    if kind == "aggTrade":
        side = "SELL" if data.get("m") else "BUY"
        return [MarketEvent(kind="trade", payload={"side": side, "price": Decimal(data["p"]), "size": Decimal(data["q"])}, **common)]
    if kind == "24hrTicker":
        return [MarketEvent(kind="ticker", payload={"price": Decimal(data["c"]), "bid": Decimal(data["b"]), "ask": Decimal(data["a"]), "volume_24h": Decimal(data["q"])}, **common)]
    return []


def decode_okx_message(message: dict, *, received_ms: int) -> list[MarketEvent]:
    arg = message.get("arg", {})
    symbol = normalize_symbol(arg.get("instId", ""))
    channel = arg.get("channel")
    events: list[MarketEvent] = []
    for row in message.get("data", []):
        common = {"exchange": "okx", "symbol": symbol, "exchange_time": _time(row.get("ts", received_ms)), "received_at": _received(received_ms)}
        if channel == "tickers":
            events.append(MarketEvent(kind="ticker", payload={"price": Decimal(row["last"]), "bid": Decimal(row["bidPx"]), "ask": Decimal(row["askPx"]), "volume_24h": Decimal(row.get("volCcy24h", "0"))}, **common))
        elif channel == "open-interest":
            events.append(MarketEvent(kind="open_interest", payload={"value": Decimal(row["oiCcy"])}, **common))
        elif channel == "trades":
            events.append(MarketEvent(kind="trade", payload={"side": row["side"].upper(), "price": Decimal(row["px"]), "size": Decimal(row["sz"])}, **common))
    return events


def decode_bybit_message(message: dict, *, received_ms: int) -> list[MarketEvent]:
    topic = message.get("topic", "")
    data = message.get("data", {})
    rows = data if isinstance(data, list) else [data]
    events: list[MarketEvent] = []
    for row in rows:
        symbol = normalize_symbol(row.get("symbol") or row.get("s") or topic.rsplit(".", 1)[-1])
        common = {"exchange": "bybit", "symbol": symbol, "exchange_time": _time(row.get("T", message.get("ts", received_ms))), "received_at": _received(received_ms)}
        if topic.startswith("tickers."):
            events.append(MarketEvent(kind="ticker", payload={"price": Decimal(row["lastPrice"]), "bid": Decimal(row["bid1Price"]), "ask": Decimal(row["ask1Price"]), "volume_24h": Decimal(row.get("turnover24h", "0"))}, **common))
            if row.get("openInterest") is not None:
                events.append(MarketEvent(kind="open_interest", payload={"value": Decimal(row["openInterest"])}, **common))
            if row.get("fundingRate") is not None:
                events.append(MarketEvent(kind="funding", payload={"value": Decimal(row["fundingRate"])}, **common))
        elif topic.startswith("publicTrade."):
            events.append(MarketEvent(kind="trade", payload={"side": row["S"].upper(), "price": Decimal(row["p"]), "size": Decimal(row["v"])}, **common))
    return events


class ExchangeAdapter(Protocol):
    name: str

    async def events(self, symbols: Sequence[str]) -> AsyncIterator[MarketEvent]: ...


class PublicWebSocketAdapter:
    def __init__(self, name: str, url: str, subscriptions: list[dict], decoder) -> None:
        self.name = name
        self.url = url
        self.subscriptions = subscriptions
        self.decoder = decoder

    async def events(self, symbols: Sequence[str]) -> AsyncIterator[MarketEvent]:
        del symbols
        async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as socket:
            for subscription in self.subscriptions:
                await socket.send(json.dumps(subscription))
            async for raw in socket:
                received_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
                for event in self.decoder(json.loads(raw), received_ms=received_ms):
                    yield event

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from crypto_signal_terminal.domain.models import DataHealth, FrozenModel, MarketSnapshot


class StaleMarketData(RuntimeError):
    pass


class MarketEvent(FrozenModel):
    exchange: str
    symbol: str
    kind: Literal["ticker", "book_snapshot", "book_delta", "trade", "open_interest", "funding", "candle"]
    exchange_time: datetime
    received_at: datetime
    sequence: int | None = None
    payload: dict[str, Decimal | int | str | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_timestamps(self) -> MarketEvent:
        if self.exchange_time.tzinfo is None or self.received_at.tzinfo is None:
            raise ValueError("market event timestamps must be timezone aware")
        return self


class _SymbolState:
    def __init__(self) -> None:
        self.exchange = ""
        self.values: dict[str, Decimal | int | bool | str] = {}
        self.last_seen: dict[str, datetime] = {}
        self.book_sequence: int | None = None
        self.book_gap = False
        self.buy_trades: deque[tuple[datetime, Decimal]] = deque(maxlen=2000)
        self.sell_trades: deque[tuple[datetime, Decimal]] = deque(maxlen=2000)


class MarketState:
    def __init__(self, *, stale_after: timedelta = timedelta(seconds=5)) -> None:
        self.stale_after = stale_after
        self._symbols: defaultdict[str, _SymbolState] = defaultdict(_SymbolState)

    def apply(self, event: MarketEvent) -> None:
        state = self._symbols[event.symbol]
        state.exchange = event.exchange
        state.last_seen[event.kind] = event.received_at
        payload = event.payload

        if event.kind == "ticker":
            state.values.update({key: Decimal(str(payload[key])) for key in ("price", "bid", "ask") if key in payload})
            if "volume_24h" in payload:
                state.values["volume_24h"] = Decimal(str(payload["volume_24h"]))
        elif event.kind in {"book_snapshot", "book_delta"}:
            if event.kind == "book_delta" and state.book_sequence is not None and event.sequence != state.book_sequence + 1:
                state.book_gap = True
            if event.kind == "book_snapshot":
                state.book_gap = False
            if event.sequence is not None:
                state.book_sequence = event.sequence
            state.values.update({key: Decimal(str(payload[key])) for key in ("bid", "ask", "bid_size", "ask_size") if key in payload})
        elif event.kind == "open_interest":
            previous = state.values.get("open_interest")
            state.values["previous_open_interest"] = previous if isinstance(previous, Decimal) else Decimal("0")
            state.values["open_interest"] = Decimal(str(payload["value"]))
        elif event.kind == "funding":
            state.values["funding_rate"] = Decimal(str(payload["value"]))
        elif event.kind == "trade":
            size = Decimal(str(payload["size"]))
            target = state.buy_trades if str(payload["side"]).upper() == "BUY" else state.sell_trades
            target.append((event.received_at, size))
        elif event.kind == "candle":
            for key, value in payload.items():
                state.values[f"candle_{key}"] = Decimal(str(value)) if key not in {"closed", "timeframe"} else value

    def health(self, symbol: str, now: datetime) -> DataHealth:
        state = self._symbols.get(symbol)
        if state is None:
            return DataHealth(healthy=False, observed_at=now, stale_sources=("missing_symbol",), reason="No market data")
        stale: list[str] = []
        for required in ("ticker", "open_interest"):
            seen = state.last_seen.get(required)
            if seen is None or now - seen > self.stale_after:
                stale.append(required)
        if state.book_gap:
            stale.append("book_sequence_gap")
        latest = max(state.last_seen.values(), default=now)
        latency_ms = max(0, int((now - latest).total_seconds() * 1000))
        return DataHealth(
            healthy=not stale,
            observed_at=latest,
            latency_ms=latency_ms,
            stale_sources=tuple(stale),
            reason=None if not stale else "Market data is stale or incomplete",
        )

    def snapshot(self, symbol: str, now: datetime) -> MarketSnapshot:
        health = self.health(symbol, now)
        if not health.healthy:
            raise StaleMarketData(f"stale market data for {symbol}: {', '.join(health.stale_sources)}")
        state = self._symbols[symbol]
        values = state.values
        price = Decimal(str(values["price"]))
        bid = Decimal(str(values.get("bid", price)))
        ask = Decimal(str(values.get("ask", price)))
        buy_volume = sum((size for _, size in state.buy_trades), Decimal("0"))
        sell_volume = sum((size for _, size in state.sell_trades), Decimal("0"))
        features = dict(values)
        features["buy_volume"] = buy_volume
        features["sell_volume"] = sell_volume
        return MarketSnapshot(
            symbol=symbol,
            exchange=state.exchange,
            observed_at=health.observed_at,
            price=price,
            bid=bid,
            ask=ask,
            open_interest=Decimal(str(values["open_interest"])),
            funding_rate=Decimal(str(values.get("funding_rate", "0"))),
            volume_24h=Decimal(str(values.get("volume_24h", "0"))),
            features=features,
            data_health=health,
        )

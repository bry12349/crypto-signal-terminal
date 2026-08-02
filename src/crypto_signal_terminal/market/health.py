from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

from crypto_signal_terminal.domain.models import MarketSnapshot


@dataclass(frozen=True)
class SymbolHealth:
    symbol: str
    status: str
    observed_at: datetime
    latency_ms: int = 0
    reason: str | None = None

    def model_dump(self) -> dict:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "observed_at": self.observed_at.isoformat(),
            "latency_ms": self.latency_ms,
            "reason": self.reason,
        }


def classify_market_error(error: Exception) -> str:
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(error, (ValueError, KeyError, TypeError)):
        return "invalid_payload"
    if isinstance(error, (httpx.HTTPError, RuntimeError)):
        return "upstream_error"
    return "unknown"


class MarketHealthRegistry:
    def __init__(self, *, watchlist: tuple[str, ...] = ()) -> None:
        self._watchlist = tuple(dict.fromkeys(symbol.upper() for symbol in watchlist))
        self._records: dict[str, SymbolHealth] = {}

    def set_watchlist(self, watchlist: tuple[str, ...]) -> None:
        self._watchlist = tuple(dict.fromkeys(symbol.upper() for symbol in watchlist))

    def record_success(self, snapshot: MarketSnapshot) -> None:
        health = snapshot.data_health
        self._records[snapshot.symbol] = SymbolHealth(
            symbol=snapshot.symbol,
            status="healthy" if health.healthy else "degraded",
            observed_at=health.observed_at,
            latency_ms=health.latency_ms,
            reason=health.reason,
        )

    def record_failure(self, symbol: str, *, observed_at: datetime, reason: str) -> None:
        normalized = symbol.upper()
        self._records[normalized] = SymbolHealth(
            symbol=normalized,
            status="unavailable",
            observed_at=observed_at,
            reason=reason,
        )

    @property
    def overall(self) -> str:
        expected = self._watchlist or tuple(self._records)
        if not expected or not self._records:
            return "connecting"
        return "healthy" if all(
            (record := self._records.get(symbol)) is not None and record.status == "healthy"
            for symbol in expected
        ) else "degraded"

    def is_tradable(self, symbol: str, *, now: datetime, max_age_seconds: int = 30) -> bool:
        record = self._records.get(symbol.upper())
        if record is None or record.status != "healthy":
            return False
        age_seconds = max(0.0, (now - record.observed_at).total_seconds())
        return age_seconds <= max_age_seconds

    def snapshot(self) -> dict:
        expected = self._watchlist or tuple(self._records)
        symbols = {
            symbol: (
                self._records[symbol].model_dump()
                if symbol in self._records
                else {
                    "symbol": symbol,
                    "status": "unknown",
                    "observed_at": None,
                    "latency_ms": 0,
                    "reason": "not_observed",
                }
            )
            for symbol in expected
        }
        healthy_count = sum(1 for item in symbols.values() if item["status"] == "healthy")
        return {
            "overall": self.overall,
            "healthy_count": healthy_count,
            "expected_count": len(expected),
            "symbols": symbols,
        }

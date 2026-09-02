from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Callable, Literal
from xml.etree import ElementTree

import httpx

from crypto_signal_terminal.domain.models import NarrativeObservation


@dataclass(frozen=True)
class FeedSource:
    id: str
    name: str
    url: str
    kind: Literal["FORUM", "ANALYST", "COPY_TRADER", "NEWS"]
    prior: Decimal


# Public read-only feeds. They are supporting evidence only, and failures are
# isolated from the market-data loop. No Telegram functionality is reintroduced.
DEFAULT_SOURCES = (
    FeedSource("reddit-bitcoin", "Reddit r/Bitcoin", "https://www.reddit.com/r/Bitcoin/hot/.rss?limit=25", "FORUM", Decimal("0.28")),
    FeedSource("reddit-cryptocurrency", "Reddit r/CryptoCurrency", "https://www.reddit.com/r/CryptoCurrency/hot/.rss?limit=25", "FORUM", Decimal("0.25")),
    FeedSource("coin-bureau", "Coin Bureau", "https://www.youtube.com/feeds/videos.xml?channel_id=UCqK_GSMbpiV8spgD3ZGloSw", "ANALYST", Decimal("0.52")),
    FeedSource("into-the-cryptoverse", "Into The Cryptoverse", "https://www.youtube.com/feeds/videos.xml?channel_id=UCRvqjQPSeaWn-uEx-w0XOIg", "ANALYST", Decimal("0.58")),
)


def sources_from_environment() -> tuple[FeedSource, ...]:
    """Add verified public feeds without embedding credentials in the app."""
    raw = os.getenv("CST_NARRATIVE_FEEDS")
    if not raw:
        return DEFAULT_SOURCES
    try:
        rows = json.loads(raw)
        allowed = {"FORUM", "ANALYST", "COPY_TRADER", "NEWS"}
        values: list[FeedSource] = []
        for row in rows if isinstance(rows, list) else ():
            if not isinstance(row, dict) or str(row.get("kind", "")).upper() not in allowed:
                continue
            try:
                prior = Decimal(str(row["prior"]))
                if not Decimal("0") <= prior <= Decimal("1"):
                    continue
                values.append(FeedSource(
                    id=str(row["id"]), name=str(row["name"]), url=str(row["url"]),
                    kind=str(row["kind"]).upper(), prior=prior,
                ))
            except (KeyError, TypeError, ValueError, ArithmeticError):
                continue
        return tuple(values) or DEFAULT_SOURCES
    except (TypeError, ValueError, json.JSONDecodeError):
        return DEFAULT_SOURCES


_BULLISH = (
    "bullish", "breakout", "break out", "rally", "surge", "upside", "accumulation",
    "buy signal", "long setup", "recovery", "bottomed", "看多", "突破", "上涨", "反弹", "吸筹",
)
_BEARISH = (
    "bearish", "breakdown", "break down", "crash", "dump", "downside", "distribution",
    "sell signal", "short setup", "rejection", "topped", "看空", "跌破", "下跌", "瀑布", "派发",
)
_ALIASES = {
    "BTC": ("btc", "bitcoin", "比特币"),
    "ETH": ("eth", "ethereum", "ether", "以太坊"),
    "SOL": ("sol", "solana"),
    "BNB": ("bnb", "binance coin"),
    "XRP": ("xrp", "ripple"),
    "DOGE": ("doge", "dogecoin"),
    "ADA": ("ada", "cardano"),
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(node: ElementTree.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        if _local(child.tag) in names and child.text:
            return child.text.strip()
    return ""


def _published(value: str, fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return fallback
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _contains(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9]+", term):
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def _stance(text: str) -> tuple[Decimal, Decimal] | None:
    lowered = re.sub(r"<[^>]+>", " ", text.lower())
    bulls = sum(_contains(lowered, term) for term in _BULLISH)
    bears = sum(_contains(lowered, term) for term in _BEARISH)
    # Explicit negations reverse the most common directional phrases.
    bulls += sum(1 for term in _BEARISH if _contains(lowered, f"not {term}"))
    bears += sum(1 for term in _BULLISH if _contains(lowered, f"not {term}"))
    if bulls == bears:
        return None
    net = Decimal(bulls - bears) / Decimal(max(2, bulls + bears))
    confidence = min(Decimal("0.75"), Decimal("0.40") + abs(net) * Decimal("0.30"))
    return max(Decimal("-1"), min(Decimal("1"), net)), confidence


def _symbols(text: str, watchlist: tuple[str, ...]) -> tuple[str, ...]:
    lowered = text.lower()
    found: list[str] = []
    for symbol in watchlist:
        base = symbol[:-4] if symbol.endswith("USDT") else symbol
        aliases = _ALIASES.get(base, (base.lower(),))
        if any(_contains(lowered, alias) for alias in aliases):
            found.append(symbol)
    return tuple(dict.fromkeys(found))


class PublicNarrativeClient:
    """Fetch public forum/analyst feeds with caching and bounded failure."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        sources: tuple[FeedSource, ...] = DEFAULT_SOURCES,
        refresh_seconds: int = 180,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(4, connect=2),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            headers={"user-agent": "CryptoSignalTerminal/0.7 (public research feed)"},
            follow_redirects=True,
        )
        self.sources = sources
        self.refresh_seconds = max(0, refresh_seconds)
        self.clock = clock
        self._cache: tuple[NarrativeObservation, ...] = ()
        self._next_refresh = 0.0

    async def _source(self, source: FeedSource, watchlist: tuple[str, ...]) -> list[NarrativeObservation]:
        response = await self.client.get(source.url)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        now = self.clock()
        values: list[NarrativeObservation] = []
        for node in root.iter():
            if _local(node.tag) not in {"entry", "item"}:
                continue
            title = _text(node, ("title",))
            summary = _text(node, ("summary", "description", "content"))
            combined = f"{title} {summary}".strip()
            direction = _stance(combined)
            targets = _symbols(combined, watchlist)
            if direction is None or not targets:
                continue
            published = _published(_text(node, ("published", "updated", "pubDate")), now)
            external_id = _text(node, ("id", "guid")) or hashlib.sha256(combined.encode()).hexdigest()[:20]
            link = next((child.attrib.get("href") for child in node.iter() if _local(child.tag) == "link" and child.attrib.get("href")), None)
            values.append(NarrativeObservation(
                id=f"{source.id}:{external_id}", source_id=source.id, source_name=source.name,
                source_kind=source.kind, published_at=published, symbols=targets,
                stance=direction[0], confidence=direction[1], source_prior=source.prior,
                text=title[:500], url=link,
            ))
        return values

    async def observe(self, watchlist: tuple[str, ...]) -> tuple[NarrativeObservation, ...]:
        loop = asyncio.get_running_loop()
        if loop.time() < self._next_refresh:
            return self._cache
        results = await asyncio.gather(*(self._source(source, watchlist) for source in self.sources), return_exceptions=True)
        fresh = tuple(item for result in results if isinstance(result, list) for item in result)
        if fresh:
            self._cache = fresh
        self._next_refresh = loop.time() + self.refresh_seconds
        return self._cache

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

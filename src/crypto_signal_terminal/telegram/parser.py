from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation

from crypto_signal_terminal.domain.models import Direction, TelegramSignal


_KEYWORDS = {
    "LONG", "SHORT", "BUY", "SELL", "ENTRY", "ENTER", "SL", "STOP", "LOSS", "TP", "TARGET", "LEVERAGE"
}


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("—", "-").replace("–", "-")


def _number(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _numbers(value: str) -> tuple[Decimal, ...]:
    found: list[Decimal] = []
    for raw in re.findall(r"(?<![A-Z])\d+(?:,\d{3})*(?:\.\d+)?", value, flags=re.I):
        parsed = _number(raw)
        if parsed is not None:
            found.append(parsed)
    return tuple(found)


def _symbol(text: str) -> str | None:
    for match in re.finditer(r"\b([A-Z]{2,12})(?:[/\-]?USDT)?\b", text.upper()):
        token = match.group(1)
        if token in _KEYWORDS or token == "USDT":
            continue
        if token.endswith("USDT") and len(token) > 4:
            return token
        return f"{token}USDT"
    return None


def _direction(text: str) -> Direction | None:
    upper = text.upper()
    long_match = re.search(r"(?:做多|开多|看多|\bLONG\b|\bBUY\b|(?:^|\s)多(?:\s|$))", upper)
    short_match = re.search(r"(?:做空|开空|看空|\bSHORT\b|\bSELL\b|(?:^|\s)空(?:\s|$))", upper)
    if bool(long_match) == bool(short_match):
        return None
    return Direction.LONG if long_match else Direction.SHORT


def _entry(text: str) -> tuple[Decimal | None, Decimal | None]:
    patterns = [
        r"(?:ENTRY|ENTER|入场|进场|开仓|买入|卖出)\s*[:：]?\s*(\d+(?:\.\d+)?)(?:\s*[-~至]\s*(\d+(?:\.\d+)?))?",
        r"(?:\bLONG\b|\bSHORT\b|做多|做空|开多|开空|(?:^|\s)[多空](?:\s|$))\s*[:：]?\s*(\d+(?:\.\d+)?)(?:\s*[-~至]\s*(\d+(?:\.\d+)?))?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            first = _number(match.group(1))
            second = _number(match.group(2)) if match.group(2) else first
            if first is not None and second is not None:
                return min(first, second), max(first, second)
    return None, None


def _stop(text: str) -> Decimal | None:
    match = re.search(r"(?:STOP\s*LOSS|\bSL\b|止损)\s*[:：]?\s*(\d+(?:\.\d+)?)", text, flags=re.I)
    return _number(match.group(1)) if match else None


def _targets(text: str) -> tuple[Decimal, ...]:
    match = re.search(
        r"(?:TAKE\s*PROFIT|TARGETS?|\bTP\d*\b|止盈)\s*[:：]?\s*(.+?)(?=(?:STOP|\bSL\b|止损|杠杆|LEVERAGE|\b\d+(?:\.\d+)?X\b|$))",
        text,
        flags=re.I,
    )
    return _numbers(match.group(1)) if match else ()


def _leverage(text: str) -> Decimal | None:
    match = re.search(r"(?:杠杆|LEVERAGE)?\s*(\d+(?:\.\d+)?)\s*[xX倍]", text, flags=re.I)
    return _number(match.group(1)) if match else None


def parse_signal(
    text: str,
    *,
    account_id: str,
    channel_id: int,
    message_id: int,
    published_at: datetime,
    edited_at: datetime | None = None,
) -> TelegramSignal:
    normalized = _normalize(text)
    symbol = _symbol(normalized)
    direction = _direction(normalized)
    entry_low, entry_high = _entry(normalized)
    stop = _stop(normalized)
    targets = _targets(normalized)
    leverage = _leverage(normalized)
    issues: list[str] = []
    if symbol is None:
        issues.append("missing_symbol")
    if direction is None:
        issues.append("missing_direction")
    if entry_low is None:
        issues.append("missing_entry")
    if stop is None:
        issues.append("missing_stop")
    if not targets:
        issues.append("missing_targets")
    required_present = 5 - sum(issue.startswith("missing_") for issue in issues)
    confidence = int(required_present / 5 * 100)
    return TelegramSignal(
        account_id=account_id,
        channel_id=channel_id,
        message_id=message_id,
        published_at=published_at,
        edited_at=edited_at,
        raw_text=normalized,
        symbol=symbol,
        direction=direction,
        entry_low=entry_low,
        entry_high=entry_high,
        stop=stop,
        targets=targets,
        leverage=leverage,
        parse_confidence=confidence,
        issues=tuple(issues),
    )

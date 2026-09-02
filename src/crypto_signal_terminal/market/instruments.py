from __future__ import annotations

from crypto_signal_terminal.domain.models import AssetClass


# Bybit TradFi perpetuals use the same USDT symbol convention as crypto
# perpetuals (for example XAUUSDT and TSLAUSDT). Keep the mapping explicit so
# an unknown ticker never silently enters a non-crypto model.
COMMODITY_SYMBOLS = (
    "XAUUSDT", "XAGUSDT", "XPTUSDT", "XPDUSDT", "XAUTUSDT",
)
US_EQUITY_SYMBOLS = (
    "AAPLUSDT", "AMZNUSDT", "GOOGLUSDT", "METAUSDT", "MSFTUSDT", "NVDAUSDT",
    "TSLAUSDT", "NFLXUSDT", "AVGOUSDT", "ORCLUSDT", "COINUSDT", "MSTRUSDT",
    "PLTRUSDT", "MUUSDT", "INTCUSDT", "AMDUSDT", "SPYUSDT", "QQQUSDT",
    "SPXUSDT", "NQUSDT",
)

DEFAULT_COMMODITY_WATCHLIST = ("XAUUSDT", "XAGUSDT")
DEFAULT_US_EQUITY_WATCHLIST = ("AAPLUSDT", "NVDAUSDT", "TSLAUSDT", "MSFTUSDT", "AMZNUSDT", "SPXUSDT")


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().replace("/", "").replace("-", "")


def asset_class_for_symbol(symbol: str) -> AssetClass:
    normalized = normalize_symbol(symbol)
    if normalized in COMMODITY_SYMBOLS:
        return AssetClass.COMMODITY
    if normalized in US_EQUITY_SYMBOLS:
        return AssetClass.US_EQUITY
    return AssetClass.CRYPTO


def watchlist_for_asset_class(asset_class: AssetClass) -> tuple[str, ...]:
    if asset_class is AssetClass.COMMODITY:
        return DEFAULT_COMMODITY_WATCHLIST
    if asset_class is AssetClass.US_EQUITY:
        return DEFAULT_US_EQUITY_WATCHLIST
    return ()

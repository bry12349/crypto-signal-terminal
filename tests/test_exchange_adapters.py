from decimal import Decimal

from crypto_signal_terminal.adapters.exchanges import (
    decode_binance_message,
    decode_bybit_message,
    decode_okx_message,
    normalize_symbol,
)


def test_normalize_symbol_removes_exchange_separators() -> None:
    assert normalize_symbol("BTC-USDT-SWAP") == "BTCUSDT"
    assert normalize_symbol("btc/usdt:usdt") == "BTCUSDT"


def test_decode_binance_book_ticker() -> None:
    events = decode_binance_message(
        {"e": "bookTicker", "E": 1754035200000, "s": "BTCUSDT", "u": 42, "b": "100", "B": "5", "a": "101", "A": "4"},
        received_ms=1754035200001,
    )
    assert events[0].kind == "book_snapshot"
    assert events[0].payload["bid"] == Decimal("100")


def test_decode_okx_ticker() -> None:
    events = decode_okx_message(
        {"arg": {"channel": "tickers", "instId": "ETH-USDT-SWAP"}, "data": [{"ts": "1754035200000", "last": "2500", "bidPx": "2499", "askPx": "2501"}]},
        received_ms=1754035200002,
    )
    assert events[0].symbol == "ETHUSDT"
    assert events[0].kind == "ticker"


def test_decode_bybit_ticker_with_open_interest() -> None:
    events = decode_bybit_message(
        {"topic": "tickers.SOLUSDT", "ts": 1754035200000, "data": {"symbol": "SOLUSDT", "lastPrice": "150", "bid1Price": "149.9", "ask1Price": "150.1", "openInterest": "900000", "fundingRate": "0.0001"}},
        received_ms=1754035200002,
    )
    kinds = {item.kind for item in events}
    assert {"ticker", "open_interest", "funding"} <= kinds

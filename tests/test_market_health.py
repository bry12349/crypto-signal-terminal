from datetime import UTC, datetime, timedelta

from crypto_signal_terminal.main import _market
from crypto_signal_terminal.market.health import MarketHealthRegistry, classify_market_error


NOW = datetime(2026, 8, 2, 5, 0, tzinfo=UTC)


def test_registry_tracks_each_symbol_and_derives_overall_health() -> None:
    registry = MarketHealthRegistry(watchlist=("BTCUSDT", "ETHUSDT"))
    assert registry.overall == "connecting"

    registry.record_success(_market("BTCUSDT", "67000"))
    registry.record_failure("ETHUSDT", observed_at=NOW, reason="timeout")

    payload = registry.snapshot()
    assert registry.overall == "degraded"
    assert payload["healthy_count"] == 1
    assert payload["expected_count"] == 2
    assert payload["symbols"]["BTCUSDT"]["status"] == "healthy"
    assert payload["symbols"]["ETHUSDT"]["reason"] == "timeout"


def test_tradeability_requires_healthy_recent_symbol_observation() -> None:
    registry = MarketHealthRegistry(watchlist=("BTCUSDT",))
    snapshot = _market("BTCUSDT", "67000").model_copy(
        update={"observed_at": NOW, "data_health": _market("BTCUSDT", "67000").data_health.model_copy(update={"observed_at": NOW})}
    )
    registry.record_success(snapshot)

    assert registry.is_tradable("BTCUSDT", now=NOW + timedelta(seconds=30)) is True
    assert registry.is_tradable("BTCUSDT", now=NOW + timedelta(seconds=31)) is False
    assert registry.is_tradable("ETHUSDT", now=NOW) is False


def test_error_classification_never_exposes_upstream_detail() -> None:
    assert classify_market_error(TimeoutError("token=secret")) == "timeout"
    assert classify_market_error(ValueError("private payload")) == "invalid_payload"
    assert classify_market_error(RuntimeError("api response with secret")) == "upstream_error"

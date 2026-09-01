import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from crypto_signal_terminal.api import ApplicationState, create_app
from crypto_signal_terminal.config import MemorySecretStore
from crypto_signal_terminal.main import build_demo_state, build_live_state, parent_is_gone, parse_args, run_demo_replay, secret_store_for_mode
from crypto_signal_terminal.storage import AuditStore
from crypto_signal_terminal.domain.models import Candle
from crypto_signal_terminal.engines.signal_ledger import SignalOutcome, SignalRecord


def test_snapshot_exposes_all_signal_paths_without_secrets() -> None:
    app = create_app(build_demo_state())
    body = TestClient(app).get("/api/v1/snapshot").json()
    serialized = json.dumps(body).lower()
    assert len(body["opportunities"]) >= 2
    assert len(body["smart_money"]) >= 1
    assert "dune-secret" not in serialized


def test_candle_endpoint_requests_the_selected_exchange_interval() -> None:
    class Market:
        async def candles(self, symbol: str, interval: str, limit: int):
            assert (symbol, interval, limit) == ("BTCUSDT", "60", 300)
            return (Candle(timestamp=1_700_000_000, open="100", high="101", low="99", close="100.5", volume="42"),)

    state = build_live_state()
    state.market_provider = Market()
    response = TestClient(create_app(state)).get("/api/v1/markets/BTCUSDT/candles", params={"interval": "60"})
    assert response.status_code == 200
    assert response.json()[0]["timestamp"] == 1_700_000_000


def test_onchain_candle_endpoint_requests_bsc_token_history() -> None:
    class OnchainMarket:
        async def candles(self, token_address: str, interval: str, limit: int):
            assert (token_address, interval, limit) == ("0xtoken", "60", 300)
            return (Candle(timestamp=1_700_000_000, open="1", high="2", low="0.5", close="1.5", volume="42"),)

    state = build_live_state()
    state.onchain_market_provider = OnchainMarket()
    response = TestClient(create_app(state)).get("/api/v1/onchain/bsc/0xtoken/candles", params={"interval": "60"})
    assert response.status_code == 200
    assert response.json()[0]["close"] == "1.5"


def test_derivatives_endpoint_exposes_real_open_interest_and_funding_series() -> None:
    class Market:
        async def derivatives(self, symbol: str, interval: str, limit: int):
            assert (symbol, interval, limit) == ("BTCUSDT", "60", 200)
            return {"open_interest": [{"time": 1_700_000_000, "value": "123"}], "funding": [{"time": 1_700_000_000, "value": "0.0001"}]}

    state = build_live_state()
    state.market_provider = Market()
    response = TestClient(create_app(state)).get("/api/v1/markets/BTCUSDT/derivatives", params={"interval": "60"})
    assert response.status_code == 200
    assert response.json()["open_interest"][0]["value"] == "123"


def test_cycle_endpoint_returns_a_conclusion_from_live_block_height() -> None:
    class Height:
        async def tip_height(self) -> int:
            return 840_000

    state = build_live_state()
    state.cycle_height_provider = Height()
    response = TestClient(create_app(state)).get("/api/v1/cycle/btc")
    assert response.status_code == 200
    assert response.json()["height"] == 840_000
    assert response.json()["phase"] == "BULL_MID"


def test_cycle_endpoint_does_not_fabricate_a_height_when_source_fails() -> None:
    class Height:
        async def tip_height(self) -> int:
            raise TimeoutError("unavailable")

    state = build_live_state()
    state.cycle_height_provider = Height()
    assert TestClient(create_app(state)).get("/api/v1/cycle/btc").status_code == 503


def test_health_reports_demo_integrations_as_optional() -> None:
    app = create_app(build_demo_state())
    body = TestClient(app).get("/api/v1/health").json()
    assert body["mode"] == "demo"
    assert body["market"] == "healthy"
    assert body["market_detail"]["healthy_count"] == 2
    assert body["market_detail"]["expected_count"] == 2


def test_settings_status_only_returns_booleans() -> None:
    state = ApplicationState(mode="demo", credentials={"dune": False})
    body = TestClient(create_app(state)).get("/api/v1/settings/status").json()
    assert body == {"dune": False}
    assert all(isinstance(value, bool) for value in body.values())


def test_same_demo_replay_produces_same_ids() -> None:
    first = run_demo_replay()
    second = run_demo_replay()
    assert first == second
    assert any(item.startswith("trend:") for item in first)
    assert any(item.startswith("alt:") for item in first)
    assert any(item.startswith("smart-flow:") for item in first)


def test_paper_order_endpoint_records_complete_plan() -> None:
    state = build_demo_state()
    client = TestClient(create_app(state, clock=lambda: state.opportunities[0].updated_at))
    opportunity = next(item for item in state.opportunities if item.order_plan is not None)
    response = client.post("/api/v1/paper-orders", json={"opportunity_id": opportunity.id})
    assert response.status_code == 201
    assert response.json()["status"] == "PREPARED"
    assert response.json()["plan"]["stop"]


def test_live_paper_order_rejects_stale_symbol_health() -> None:
    state = build_demo_state()
    state.mode = "live"
    opportunity = next(item for item in state.opportunities if item.order_plan is not None)
    client = TestClient(create_app(
        state,
        clock=lambda: opportunity.updated_at + timedelta(seconds=31),
    ))
    response = client.post("/api/v1/paper-orders", json={"opportunity_id": opportunity.id})
    assert response.status_code == 409
    assert response.json()["detail"] == "Symbol market data is stale or unavailable"


def test_live_paper_order_rejects_unhealthy_original_opportunity() -> None:
    state = build_demo_state()
    state.mode = "live"
    opportunity = next(item for item in state.opportunities if item.order_plan is not None)
    state.opportunities = [
        item.model_copy(update={"data_health": item.data_health.model_copy(update={"healthy": False})})
        if item.id == opportunity.id else item
        for item in state.opportunities
    ]
    client = TestClient(create_app(state, clock=lambda: opportunity.updated_at))
    response = client.post("/api/v1/paper-orders", json={"opportunity_id": opportunity.id})
    assert response.status_code == 409
    assert response.json()["detail"] == "Opportunity was produced from unhealthy market data"


def test_paper_order_is_persisted_and_available_from_history(tmp_path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    state = build_demo_state()
    opportunity = next(item for item in state.opportunities if item.order_plan is not None)
    client = TestClient(create_app(state, audit_store=store, clock=lambda: opportunity.updated_at))

    prepared = client.post("/api/v1/paper-orders", json={"opportunity_id": opportunity.id})
    history = client.get("/api/v1/paper-orders").json()

    assert prepared.status_code == 201
    assert history[0]["id"] == prepared.json()["id"]
    assert history[0]["symbol"] == opportunity.symbol
    assert AuditStore(tmp_path / "audit.sqlite3").paper_orders()[0]["id"] == prepared.json()["id"]


def test_performance_endpoint_reports_settled_signal_results(tmp_path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    state = build_demo_state()
    opportunity = next(item for item in state.opportunities if item.order_plan is not None)
    store.upsert_signal_record(replace(
        SignalRecord(signal_id="trend:btc:performance", symbol="BTCUSDT", plan=opportunity.order_plan, generated_at=opportunity.created_at, predicted_probability=Decimal("0.68")),
        outcome=SignalOutcome.TP1,
        settled_at=opportunity.updated_at,
    ))

    response = TestClient(create_app(state, audit_store=store)).get("/api/v1/performance")

    assert response.status_code == 200
    assert response.json()["settled"] == 1
    assert response.json()["wins"] == 1
    assert response.json()["win_rate"] == 1.0
    assert response.json()["calibration"] == [{"bucket": "0.6-0.7", "count": 1, "predicted": 0.68, "observed": 1.0}]
    assert response.json()["calibration_state"] == {
        "settled": 1,
        "mean_predicted": 0.68,
        "observed_win_rate": 1.0,
        "absolute_error": 0.32,
        "brier_score": 0.1024,
        "status": "INSUFFICIENT",
    }


def test_calibration_degrades_when_individual_probabilities_are_wrong_despite_matching_averages(tmp_path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    opportunity = next(item for item in build_demo_state().opportunities if item.order_plan is not None)
    for index in range(30):
        predicted = Decimal("0.90") if index < 15 else Decimal("0.10")
        outcome = SignalOutcome.STOP if index < 15 else SignalOutcome.TP1
        store.upsert_signal_record(SignalRecord(
            signal_id=f"brier:{index}", symbol="BTCUSDT", plan=opportunity.order_plan,
            generated_at=opportunity.created_at, predicted_probability=predicted,
            signal_type="trend_continuation", outcome=outcome, settled_at=opportunity.updated_at,
        ))

    calibration = store.calibration_state(signal_type="trend_continuation", direction=opportunity.order_plan.direction)

    assert calibration["mean_predicted"] == 0.5
    assert calibration["observed_win_rate"] == 0.5
    assert calibration["absolute_error"] == 0.0
    assert calibration["brier_score"] == 0.81
    assert calibration["status"] == "DEGRADED"


def test_calibration_uses_a_recent_rolling_window_instead_of_permanent_old_regimes(tmp_path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    opportunity = next(item for item in build_demo_state().opportunities if item.order_plan is not None)
    for index in range(100):
        store.upsert_signal_record(SignalRecord(
            signal_id=f"old-regime:{index}", symbol="BTCUSDT", plan=opportunity.order_plan,
            generated_at=opportunity.created_at - timedelta(days=100, seconds=index), predicted_probability=Decimal("0.70"),
            signal_type="trend_continuation", outcome=SignalOutcome.STOP, settled_at=opportunity.updated_at,
        ))
    for index in range(200):
        store.upsert_signal_record(SignalRecord(
            signal_id=f"recent-regime:{index}", symbol="BTCUSDT", plan=opportunity.order_plan,
            generated_at=opportunity.created_at + timedelta(seconds=index), predicted_probability=Decimal("0.70"),
            signal_type="trend_continuation", outcome=SignalOutcome.TP1 if index < 140 else SignalOutcome.STOP,
            settled_at=opportunity.updated_at,
        ))

    calibration = store.calibration_state(
        signal_type="trend_continuation", direction=opportunity.order_plan.direction, symbol="BTCUSDT",
    )

    assert calibration["settled"] == 200
    assert calibration["observed_win_rate"] == 0.7
    assert calibration["brier_score"] == 0.21
    assert calibration["status"] == "VALIDATED"


def test_audit_store_removes_retired_message_tables(tmp_path) -> None:
    path = tmp_path / "audit.sqlite3"
    connection = __import__("sqlite3").connect(path)
    connection.execute("CREATE TABLE telegram_message_versions (id INTEGER PRIMARY KEY)")
    connection.commit()
    connection.close()

    AuditStore(path).close()

    names = {row[0] for row in __import__("sqlite3").connect(path).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "telegram_message_versions" not in names
    assert "paper_orders" in names



def test_unknown_paper_order_is_not_found() -> None:
    client = TestClient(create_app(build_demo_state()))
    assert client.post("/api/v1/paper-orders", json={"opportunity_id": "missing"}).status_code == 404


def test_expired_paper_order_requires_fresh_analysis() -> None:
    state = build_demo_state()
    opportunity = next(item for item in state.opportunities if item.order_plan is not None)
    client = TestClient(create_app(state, clock=lambda: opportunity.order_plan.expires_at + timedelta(seconds=1)))
    response = client.post("/api/v1/paper-orders", json={"opportunity_id": opportunity.id})
    assert response.status_code == 409
    assert "expired" in response.json()["detail"].lower()


def test_event_broadcast_reaches_every_subscriber() -> None:
    import asyncio

    state = ApplicationState()
    first: asyncio.Queue = asyncio.Queue()
    second: asyncio.Queue = asyncio.Queue()
    state.subscribers.update((first, second))
    state.publish({"type": "test"})
    assert first.get_nowait() == {"type": "test"}
    assert second.get_nowait() == {"type": "test"}


def test_local_desktop_origin_is_allowed() -> None:
    client = TestClient(create_app(build_demo_state()))
    response = client.options(
        "/api/v1/snapshot",
        headers={"Origin": "http://127.0.0.1:1420", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"


def test_credential_endpoint_returns_status_not_secret() -> None:
    store = MemorySecretStore()
    state = ApplicationState(mode="demo")
    client = TestClient(create_app(state, secret_store=store))
    body = client.post(
        "/api/v1/settings/credentials",
        json={"dune_api_key": "dune-secret", "dune_query_id": 456},
    ).json()
    assert body == {"dune": True}
    assert "secret" not in json.dumps(body)
    assert store.get("dune_api_key") == "dune-secret"


def test_sidecar_port_argument_is_supported() -> None:
    assert parse_args(["--port", "9876"]).port == 9876


def test_demo_sidecar_does_not_touch_the_system_keyring() -> None:
    assert isinstance(secret_store_for_mode("demo"), MemorySecretStore)



def test_sidecar_detects_reparenting_after_desktop_exit() -> None:
    assert parent_is_gone(initial_parent=400, current_parent=1) is True
    assert parent_is_gone(initial_parent=400, current_parent=400) is False


def test_live_startup_never_contains_demo_trades() -> None:
    state = build_live_state()
    assert state.mode == "live"
    assert state.opportunities == []
    assert state.market_health == "connecting"

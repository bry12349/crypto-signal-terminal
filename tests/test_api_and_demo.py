import json

from fastapi.testclient import TestClient

from crypto_signal_terminal.api import ApplicationState, create_app
from crypto_signal_terminal.config import MemorySecretStore
from crypto_signal_terminal.main import build_demo_state, parent_is_gone, parse_args, run_demo_replay


def test_snapshot_exposes_all_signal_paths_without_secrets() -> None:
    app = create_app(build_demo_state())
    body = TestClient(app).get("/api/v1/snapshot").json()
    serialized = json.dumps(body).lower()
    assert len(body["opportunities"]) >= 2
    assert len(body["smart_money"]) >= 1
    assert len(body["confirmations"]) >= 1
    assert "api_hash" not in serialized
    assert "bot_token" not in serialized


def test_health_reports_demo_integrations_as_optional() -> None:
    app = create_app(build_demo_state())
    body = TestClient(app).get("/api/v1/health").json()
    assert body["mode"] == "demo"
    assert body["market"] == "healthy"
    assert body["telegram"] == "not_configured"


def test_settings_status_only_returns_booleans() -> None:
    state = ApplicationState(mode="demo", credentials={"telegram": True, "bot": False, "dune": False})
    body = TestClient(create_app(state)).get("/api/v1/settings/status").json()
    assert body == {"telegram": True, "bot": False, "dune": False}
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
    client = TestClient(create_app(state))
    opportunity = next(item for item in state.opportunities if item.order_plan is not None)
    response = client.post("/api/v1/paper-orders", json={"opportunity_id": opportunity.id})
    assert response.status_code == 201
    assert response.json()["status"] == "PREPARED"
    assert response.json()["plan"]["stop"]


def test_unknown_paper_order_is_not_found() -> None:
    client = TestClient(create_app(build_demo_state()))
    assert client.post("/api/v1/paper-orders", json={"opportunity_id": "missing"}).status_code == 404


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
        json={"telegram_api_id": 123, "telegram_api_hash": "hash-secret", "telegram_bot_token": "bot-secret", "telegram_chat_id": "456"},
    ).json()
    assert body == {"telegram": True, "bot": True, "dune": False}
    assert "secret" not in json.dumps(body)
    assert store.get("telegram_api_hash") == "hash-secret"


def test_sidecar_port_argument_is_supported() -> None:
    assert parse_args(["--port", "9876"]).port == 9876


def test_telegram_qr_login_requires_saved_credentials() -> None:
    client = TestClient(create_app(ApplicationState(), secret_store=MemorySecretStore()))
    response = client.post("/api/v1/telegram/login/qr")
    assert response.status_code == 409
    assert response.json()["detail"] == "telegram_credentials_missing"


def test_sidecar_detects_reparenting_after_desktop_exit() -> None:
    assert parent_is_gone(initial_parent=400, current_parent=1) is True
    assert parent_is_gone(initial_parent=400, current_parent=400) is False

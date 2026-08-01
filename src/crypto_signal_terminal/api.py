from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from crypto_signal_terminal.config import KeyringSecretStore, SecretStore
from crypto_signal_terminal.domain.models import ConfirmationResult, Opportunity, SmartMoneyCandidate
from crypto_signal_terminal.telegram.auth import TelegramLoginManager


@dataclass
class ApplicationState:
    mode: str = "demo"
    opportunities: list[Opportunity] = field(default_factory=list)
    smart_money: list[SmartMoneyCandidate] = field(default_factory=list)
    confirmations: list[ConfirmationResult] = field(default_factory=list)
    credentials: dict[str, bool] = field(default_factory=lambda: {"telegram": False, "bot": False, "dune": False})
    telegram_channels: list[dict] = field(default_factory=list)
    telegram_authorized: bool = False
    market_health: str = "healthy"
    paper_orders: list[dict] = field(default_factory=list)
    market_candles: dict[str, list[dict]] = field(default_factory=dict)
    dune_health: str = "not_configured"
    subscribers: set[asyncio.Queue] = field(default_factory=set)

    def snapshot(self) -> dict:
        return {
            "mode": self.mode,
            "opportunities": [item.model_dump(mode="json") for item in self.opportunities],
            "smart_money": [item.model_dump(mode="json") for item in self.smart_money],
            "confirmations": [item.model_dump(mode="json") for item in self.confirmations],
            "candles": self.market_candles,
        }

    def publish(self, event: dict) -> None:
        for queue in tuple(self.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                continue


class PaperOrderRequest(BaseModel):
    opportunity_id: str


class CredentialsInput(BaseModel):
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    dune_api_key: str | None = None
    dune_query_id: int | None = None


class TelegramPasswordInput(BaseModel):
    password: str


def create_app(
    state: ApplicationState | None = None,
    *,
    secret_store: SecretStore | None = None,
    background_runner: Callable[[asyncio.Event], Awaitable[None]] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
) -> FastAPI:
    runtime = state or ApplicationState()
    secrets = secret_store or KeyringSecretStore()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop = asyncio.Event()
        task = asyncio.create_task(background_runner(stop)) if background_runner else None
        try:
            yield
        finally:
            stop.set()
            if task:
                await task

    app = FastAPI(title="Crypto Signal Terminal", version="0.1.0", lifespan=lifespan)
    login_manager = TelegramLoginManager(secrets)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:1420", "http://localhost:1420", "tauri://localhost", "https://tauri.localhost"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type"],
    )
    app.state.runtime = runtime

    @app.get("/api/v1/snapshot")
    async def snapshot() -> dict:
        return runtime.snapshot()

    @app.get("/api/v1/health")
    async def health() -> dict:
        return {
            "mode": runtime.mode,
            "market": runtime.market_health,
            "telegram": "healthy" if runtime.telegram_authorized else "configured" if runtime.credentials.get("telegram") else "not_configured",
            "bot": "healthy" if runtime.credentials.get("bot") else "not_configured",
            "dune": runtime.dune_health if runtime.credentials.get("dune") else "not_configured",
        }

    @app.get("/api/v1/settings/status")
    async def settings_status() -> dict[str, bool]:
        return {key: bool(value) for key, value in runtime.credentials.items()}

    @app.post("/api/v1/settings/credentials")
    async def save_credentials(payload: CredentialsInput) -> dict[str, bool]:
        values = payload.model_dump(exclude_none=True)
        for name, value in values.items():
            secrets.set(name, str(value))
        runtime.credentials = {
            "telegram": bool(
                (values.get("telegram_api_id") or secrets.get("telegram_api_id"))
                and (values.get("telegram_api_hash") or secrets.get("telegram_api_hash"))
            ),
            "bot": bool(
                (values.get("telegram_bot_token") or secrets.get("telegram_bot_token"))
                and (values.get("telegram_chat_id") or secrets.get("telegram_chat_id"))
            ),
            "dune": bool(
                (values.get("dune_api_key") or secrets.get("dune_api_key"))
                and (values.get("dune_query_id") or secrets.get("dune_query_id"))
            ),
        }
        runtime.dune_health = "configured_not_running" if runtime.credentials["dune"] else "not_configured"
        return runtime.credentials

    @app.get("/api/v1/telegram/channels")
    async def telegram_channels() -> list[dict]:
        return runtime.telegram_channels

    @app.post("/api/v1/telegram/login/qr")
    async def telegram_login_qr() -> dict[str, str | None]:
        try:
            return await login_manager.start()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/telegram/login/status")
    async def telegram_login_status() -> dict[str, str | None]:
        result = login_manager.status()
        if result["status"] == "authorized":
            runtime.telegram_authorized = True
        elif result["status"] in {"expired", "error"}:
            runtime.telegram_authorized = False
        return result

    @app.post("/api/v1/telegram/login/password")
    async def telegram_login_password(payload: TelegramPasswordInput) -> dict[str, str | None]:
        try:
            result = await login_manager.complete_password(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        runtime.telegram_authorized = result["status"] == "authorized"
        return result

    @app.post("/api/v1/paper-orders", status_code=status.HTTP_201_CREATED)
    async def prepare_paper_order(request: PaperOrderRequest) -> dict:
        opportunity = next((item for item in runtime.opportunities if item.id == request.opportunity_id), None)
        if opportunity is None or opportunity.order_plan is None:
            raise HTTPException(status_code=404, detail="Actionable opportunity not found")
        if opportunity.order_plan.expires_at <= clock():
            raise HTTPException(status_code=409, detail="Opportunity expired; refresh market analysis")
        if runtime.mode == "live" and runtime.market_health != "healthy":
            raise HTTPException(status_code=409, detail="Market data is not fully healthy")
        record = {
            "id": f"paper:{len(runtime.paper_orders) + 1}",
            "opportunity_id": opportunity.id,
            "status": "PREPARED",
            "plan": opportunity.order_plan.model_dump(mode="json"),
        }
        runtime.paper_orders.append(record)
        return record

    @app.websocket("/api/v1/events")
    async def events(websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        runtime.subscribers.add(queue)
        await websocket.send_json({"type": "snapshot", "payload": runtime.snapshot()})
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            return
        finally:
            runtime.subscribers.discard(queue)

    return app

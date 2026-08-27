from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from crypto_signal_terminal.config import KeyringSecretStore, SecretStore
from crypto_signal_terminal.domain.models import Opportunity, SmartMoneyCandidate
from crypto_signal_terminal.market.health import MarketHealthRegistry
from crypto_signal_terminal.storage import AuditStore


@dataclass
class ApplicationState:
    mode: str = "demo"
    opportunities: list[Opportunity] = field(default_factory=list)
    smart_money: list[SmartMoneyCandidate] = field(default_factory=list)
    credentials: dict[str, bool] = field(default_factory=lambda: {"dune": False})
    market_health: str = "healthy"
    market_health_registry: MarketHealthRegistry = field(default_factory=MarketHealthRegistry)
    paper_orders: list[dict] = field(default_factory=list)
    market_candles: dict[str, list[dict]] = field(default_factory=dict)
    market_provider: Any | None = None
    dune_health: str = "not_configured"
    subscribers: set[asyncio.Queue] = field(default_factory=set)

    def snapshot(self) -> dict:
        return {
            "mode": self.mode,
            "opportunities": [item.model_dump(mode="json") for item in self.opportunities],
            "smart_money": [item.model_dump(mode="json") for item in self.smart_money],
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
    dune_api_key: str | None = None
    dune_query_id: int | None = None


def create_app(
    state: ApplicationState | None = None,
    *,
    secret_store: SecretStore | None = None,
    audit_store: AuditStore | None = None,
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

    app = FastAPI(title="Crypto Signal Terminal", version="0.5.1", lifespan=lifespan)
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
        market = runtime.market_health_registry.snapshot()
        return {
            "mode": runtime.mode,
            "market": market["overall"] if market["expected_count"] else runtime.market_health,
            "market_detail": market,
            "dune": runtime.dune_health if runtime.credentials.get("dune") else "not_configured",
        }

    @app.get("/api/v1/markets/{symbol}/candles")
    async def candles(symbol: str, interval: str = "5", limit: int = 300) -> list[dict]:
        if interval not in {"5", "15", "60", "240"}:
            raise HTTPException(status_code=422, detail="Unsupported candle interval")
        if runtime.market_provider is None:
            raise HTTPException(status_code=503, detail="Live candle source is unavailable")
        try:
            values = await runtime.market_provider.candles(symbol.upper(), interval, max(50, min(limit, 500)))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Live candle source is unavailable") from exc
        return [item.model_dump(mode="json") for item in values]

    @app.get("/api/v1/settings/status")
    async def settings_status() -> dict[str, bool]:
        return {key: bool(value) for key, value in runtime.credentials.items()}

    @app.post("/api/v1/settings/credentials")
    async def save_credentials(payload: CredentialsInput) -> dict[str, bool]:
        values = payload.model_dump(exclude_none=True)
        for name, value in values.items():
            secrets.set(name, str(value))
        runtime.credentials = {
            "dune": bool(
                (values.get("dune_api_key") or secrets.get("dune_api_key"))
                and (values.get("dune_query_id") or secrets.get("dune_query_id"))
            ),
        }
        runtime.dune_health = "configured_not_running" if runtime.credentials["dune"] else "not_configured"
        return runtime.credentials

    @app.post("/api/v1/paper-orders", status_code=status.HTTP_201_CREATED)
    async def prepare_paper_order(request: PaperOrderRequest) -> dict:
        opportunity = next((item for item in runtime.opportunities if item.id == request.opportunity_id), None)
        plan = opportunity.order_plan if opportunity is not None else None
        symbol = opportunity.symbol if opportunity is not None else None
        if plan is None or symbol is None:
            raise HTTPException(status_code=404, detail="Actionable opportunity not found")
        now = clock()
        if plan.expires_at <= now:
            raise HTTPException(status_code=409, detail="Opportunity expired; refresh market analysis")
        if opportunity is not None and not opportunity.data_health.healthy:
            raise HTTPException(status_code=409, detail="Opportunity was produced from unhealthy market data")
        if runtime.mode == "live" and not runtime.market_health_registry.is_tradable(symbol, now=now):
            raise HTTPException(status_code=409, detail="Symbol market data is stale or unavailable")
        record = {
            "id": f"paper:{uuid4().hex}",
            "opportunity_id": request.opportunity_id,
            "symbol": symbol,
            "status": "PREPARED",
            "prepared_at": now.isoformat(),
            "plan": plan.model_dump(mode="json"),
        }
        if audit_store is not None:
            audit_store.record_paper_order(record)
        runtime.paper_orders.append(record)
        return record

    @app.get("/api/v1/paper-orders")
    async def paper_orders(limit: int = 50) -> list[dict]:
        bounded = max(1, min(200, limit))
        if audit_store is not None:
            return audit_store.paper_orders(limit=bounded)
        return list(reversed(runtime.paper_orders[-bounded:]))

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

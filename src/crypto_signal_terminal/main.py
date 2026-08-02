from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import uvicorn

from crypto_signal_terminal.api import ApplicationState, create_app
from crypto_signal_terminal.confirmation import ConfirmationEngine
from crypto_signal_terminal.config import KeyringSecretStore, Settings
from crypto_signal_terminal.domain.models import DataHealth, Direction, MarketSnapshot, TelegramSignal
from crypto_signal_terminal.engines.altcoin import AltcoinEngine
from crypto_signal_terminal.engines.smart_money import SmartMoneyEngine
from crypto_signal_terminal.engines.trend import TrendEngine
from crypto_signal_terminal.market.live import BybitCompositeMarketClient
from crypto_signal_terminal.market.scanner import LiveMarketScanner
from crypto_signal_terminal.storage import AuditStore
from crypto_signal_terminal.telegram.coordinator import TelegramSignalCoordinator
from crypto_signal_terminal.telegram.notifier import TelegramBotNotifier


DEMO_TIME = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def _market(symbol: str, price: str, **features) -> MarketSnapshot:
    value = Decimal(price)
    return MarketSnapshot(
        symbol=symbol,
        exchange="demo-composite",
        observed_at=DEMO_TIME,
        price=value,
        bid=value * Decimal("0.9998"),
        ask=value * Decimal("1.0002"),
        open_interest=Decimal("100000000"),
        funding_rate=Decimal("0.0001"),
        volume_24h=Decimal("900000000"),
        data_health=DataHealth(healthy=True, observed_at=DEMO_TIME, latency_ms=42),
        peer_confirmations=3,
        features=features,
    )


def build_demo_state() -> ApplicationState:
    btc = _market(
        "BTCUSDT", "67240", trend_4h=1, trend_1h=1, setup_15m=1, trigger_5m=1,
        aggressive_flow_imbalance="0.58", oi_change_ratio="0.045", spread_bps="1.2",
    )
    sol = _market(
        "SOLUSDT", "146.35", atr_percentile=11, volume_acceleration="2.4",
        oi_change_ratio="0.08", aggressive_flow_imbalance="-0.66", depth_imbalance="-0.42",
        trigger_5m=-1, spread_bps="4.5", trend_1h=-1, large_trade_count=8,
        flow_persistence="0.84", price_impact_bps="19", absorption="0.12",
    )
    trend = TrendEngine().evaluate(btc)
    alt = AltcoinEngine().evaluate(sol)
    smart = SmartMoneyEngine().evaluate_flow(sol)
    signal = TelegramSignal(
        account_id="demo",
        channel_id=1001,
        message_id=77,
        published_at=DEMO_TIME - timedelta(seconds=12),
        raw_text="SOL short entry 146.2-146.5 sl 147.4 tp 144.6 142.9",
        symbol="SOLUSDT",
        direction=Direction.SHORT,
        entry_low=Decimal("146.2"),
        entry_high=Decimal("146.5"),
        stop=Decimal("147.4"),
        targets=(Decimal("144.6"), Decimal("142.9")),
        parse_confidence=100,
    )
    confirmation = ConfirmationEngine().confirm(signal, sol, analyzed_at=DEMO_TIME)
    state = ApplicationState(
        mode="demo",
        opportunities=[item for item in (trend, alt) if item is not None],
        smart_money=[item for item in (smart,) if item is not None],
        confirmations=[confirmation],
        credentials={"telegram": False, "bot": False, "dune": False},
        market_health="healthy",
    )
    state.market_health_registry.set_watchlist((btc.symbol, sol.symbol))
    state.market_health_registry.record_success(btc)
    state.market_health_registry.record_success(sol)
    return state


def build_live_state() -> ApplicationState:
    return ApplicationState(mode="live", market_health="connecting")


def run_demo_replay() -> tuple[str, ...]:
    state = build_demo_state()
    ids = [item.id for item in state.opportunities]
    ids.extend(item.id for item in state.smart_money)
    ids.extend(item.id for item in state.confirmations)
    return tuple(ids)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto Signal Terminal local service")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args(argv)


def parent_is_gone(*, initial_parent: int, current_parent: int) -> bool:
    return initial_parent != 1 and current_parent == 1


async def exit_when_parent_is_gone(stop: asyncio.Event) -> None:
    initial_parent = os.getppid()
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=1)
        except asyncio.TimeoutError:
            pass
        if parent_is_gone(initial_parent=initial_parent, current_parent=os.getppid()):
            os._exit(0)


def run() -> None:
    args = parse_args()
    secrets = KeyringSecretStore()
    settings = Settings.from_environment(secrets)
    state = build_demo_state() if settings.mode == "demo" else build_live_state()
    state.credentials = settings.credential_status()
    state.dune_health = "configured_not_running" if state.credentials.get("dune") else "not_configured"
    state.telegram_authorized = bool(secrets.get("telegram_session"))
    audit_key = secrets.get("audit_encryption_key")
    if not audit_key:
        audit_key = AuditStore.generate_key().decode("ascii")
        secrets.set("audit_encryption_key", audit_key)
    store = AuditStore(settings.runtime_dir.expanduser() / "audit.sqlite3", encryption_key=audit_key.encode("ascii"))
    state.paper_orders = list(reversed(store.paper_orders(limit=200)))

    def notifier_factory() -> TelegramBotNotifier | None:
        token = secrets.get("telegram_bot_token")
        chat_id = secrets.get("telegram_chat_id")
        if not token or not chat_id:
            return None
        return TelegramBotNotifier(bot_token=token, chat_id=chat_id, store=store)

    live_market = BybitCompositeMarketClient()
    coordinator = TelegramSignalCoordinator(
        state=state,
        store=store,
        market=live_market,
        secrets=secrets,
        notifier_factory=notifier_factory,
    )
    scanner = LiveMarketScanner(state=state, market=live_market)

    async def background(stop):
        services = [exit_when_parent_is_gone(stop)]
        if settings.mode != "demo":
            services.extend((coordinator.run(stop), scanner.run(stop)))
        await asyncio.gather(*services)

    uvicorn.run(
        create_app(state, secret_store=secrets, audit_store=store, background_runner=background),
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    run()

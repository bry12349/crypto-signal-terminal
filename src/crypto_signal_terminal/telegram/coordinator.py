from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from crypto_signal_terminal.config import SecretStore
from crypto_signal_terminal.confirmation import ConfirmationEngine
from crypto_signal_terminal.domain.models import ConfirmationResult, MarketSnapshot
from crypto_signal_terminal.storage import AuditStore
from crypto_signal_terminal.telegram.client import PinnedChannelMonitor, TelegramUpdate
from crypto_signal_terminal.telegram.parser import parse_signal


class MarketProvider(Protocol):
    async def snapshot(self, symbol: str) -> MarketSnapshot: ...


class TelegramSignalCoordinator:
    def __init__(
        self,
        *,
        state: Any,
        store: AuditStore,
        market: MarketProvider,
        secrets: SecretStore | None = None,
        notifier_factory: Callable[[], Any | None] | None = None,
        confirmation: ConfirmationEngine | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self.state = state
        self.store = store
        self.market = market
        self.secrets = secrets
        self.notifier_factory = notifier_factory
        self.confirmation = confirmation or ConfirmationEngine()
        self.clock = clock

    async def process_update(self, update: TelegramUpdate) -> ConfirmationResult | None:
        if update.kind == "deleted":
            self.store.mark_message_deleted("telegram-user", update.channel_id, update.message_id, update.observed_at)
            return None
        if not update.text:
            return None
        is_new_version = self.store.record_message_version(
            "telegram-user", update.channel_id, update.message_id, update.text, update.observed_at,
        )
        if not is_new_version:
            return None
        signal = parse_signal(
            update.text,
            account_id="telegram-user",
            channel_id=update.channel_id,
            message_id=update.message_id,
            published_at=update.observed_at,
            edited_at=update.edited_at,
        )
        if signal.symbol is None or signal.direction is None:
            return None
        try:
            snapshot = await self.market.snapshot(signal.symbol)
        except Exception:
            self.state.market_health = "degraded"
            return None
        self.state.market_health = "healthy"
        result = self.confirmation.confirm(signal, snapshot, analyzed_at=self.clock())
        self.state.confirmations.insert(0, result)
        del self.state.confirmations[100:]
        try:
            self.state.event_queue.put_nowait({"type": "confirmation", "payload": result.model_dump(mode="json")})
        except asyncio.QueueFull:
            pass
        notifier = self.notifier_factory() if self.notifier_factory else None
        if notifier is not None:
            await notifier.send(result)
        return result

    async def run(self, stop: asyncio.Event) -> None:
        if self.secrets is None:
            return
        while not stop.is_set():
            api_id = self.secrets.get("telegram_api_id")
            api_hash = self.secrets.get("telegram_api_hash")
            session = self.secrets.get("telegram_session")
            if not api_id or not api_hash or not session:
                await self._pause(stop, 2)
                continue
            monitor = PinnedChannelMonitor(api_id=int(api_id), api_hash=api_hash, session=session)
            try:
                await monitor.connect()
                if not await monitor.client.is_user_authorized():
                    self.state.telegram_authorized = False
                    await self._pause(stop, 2)
                    continue
                channels = await monitor.discover_pinned()
                self.state.telegram_channels = [
                    {"id": item.peer_id, "title": item.title, "enabled": True} for item in channels
                ]
                monitor.install_handlers()
                self.state.telegram_authorized = True
                while not stop.is_set():
                    try:
                        update = await asyncio.wait_for(monitor.queue.get(), timeout=1)
                    except asyncio.TimeoutError:
                        continue
                    await self.process_update(update)
            except Exception:
                self.state.telegram_authorized = False
                await self._pause(stop, 3)
            finally:
                await monitor.disconnect()

    @staticmethod
    async def _pause(stop: asyncio.Event, seconds: float) -> None:
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

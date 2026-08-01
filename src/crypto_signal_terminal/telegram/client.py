from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import AsyncIterator, Iterable

from telethon import TelegramClient, events
from telethon.sessions import StringSession


@dataclass(frozen=True)
class PinnedDialog:
    peer_id: int
    title: str
    is_channel: bool
    pinned: bool


@dataclass(frozen=True)
class TelegramUpdate:
    kind: str
    channel_id: int
    message_id: int
    text: str | None
    observed_at: datetime
    edited_at: datetime | None = None


def select_monitored_channels(dialogs: Iterable[PinnedDialog], disabled: set[int] | None = None) -> list[PinnedDialog]:
    excluded = disabled or set()
    return [item for item in dialogs if item.pinned and item.is_channel and item.peer_id not in excluded]


class PinnedChannelMonitor:
    def __init__(self, *, api_id: int, api_hash: str, session: str | None = None, disabled: set[int] | None = None) -> None:
        self.client = TelegramClient(StringSession(session), api_id, api_hash)
        self.disabled = disabled or set()
        self.queue: asyncio.Queue[TelegramUpdate] = asyncio.Queue(maxsize=1000)
        self.monitored_ids: set[int] = set()

    async def connect(self) -> None:
        await self.client.connect()

    async def discover_pinned(self) -> list[PinnedDialog]:
        dialogs: list[PinnedDialog] = []
        async for dialog in self.client.iter_dialogs():
            entity = dialog.entity
            peer_id = int(getattr(entity, "id", 0))
            dialogs.append(PinnedDialog(
                peer_id=peer_id,
                title=str(getattr(dialog, "name", "")),
                is_channel=bool(getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False)),
                pinned=bool(getattr(dialog, "pinned", False)),
            ))
        selected = select_monitored_channels(dialogs, self.disabled)
        self.monitored_ids = {item.peer_id for item in selected}
        return selected

    def install_handlers(self) -> None:
        @self.client.on(events.NewMessage)
        async def on_new(event) -> None:
            await self._enqueue_message("new", event)

        @self.client.on(events.MessageEdited)
        async def on_edit(event) -> None:
            await self._enqueue_message("edited", event)

        @self.client.on(events.MessageDeleted)
        async def on_delete(event) -> None:
            channel_id = int(getattr(event, "chat_id", 0) or 0)
            if abs(channel_id) not in self.monitored_ids and channel_id not in self.monitored_ids:
                return
            for message_id in event.deleted_ids:
                await self.queue.put(TelegramUpdate("deleted", channel_id, int(message_id), None, datetime.now(tz=UTC)))

    async def _enqueue_message(self, kind: str, event) -> None:
        channel_id = int(getattr(event, "chat_id", 0) or 0)
        entity_id = abs(channel_id)
        if entity_id not in self.monitored_ids and channel_id not in self.monitored_ids:
            return
        message = event.message
        observed = datetime.now(tz=UTC)
        await self.queue.put(TelegramUpdate(
            kind=kind,
            channel_id=channel_id,
            message_id=int(message.id),
            text=str(message.message or ""),
            observed_at=observed,
            edited_at=getattr(message, "edit_date", None),
        ))

    async def events(self) -> AsyncIterator[TelegramUpdate]:
        while True:
            yield await self.queue.get()

    def export_session(self) -> str:
        return self.client.session.save()

    async def disconnect(self) -> None:
        await self.client.disconnect()

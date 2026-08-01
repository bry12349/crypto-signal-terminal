from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import AsyncIterator, Iterable

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.utils import resolve_id


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
    published_at: datetime | None = None
    edited_at: datetime | None = None


def select_monitored_channels(dialogs: Iterable[PinnedDialog], disabled: set[int] | None = None) -> list[PinnedDialog]:
    excluded = disabled or set()
    return [item for item in dialogs if item.pinned and item.is_channel and item.peer_id not in excluded]


def normalize_peer_id(value: int) -> int:
    return int(resolve_id(value)[0])


class PinnedChannelMonitor:
    def __init__(self, *, api_id: int, api_hash: str, session: str | None = None, disabled: set[int] | None = None) -> None:
        self.client = TelegramClient(StringSession(session), api_id, api_hash)
        self.disabled = disabled or set()
        self.queue: asyncio.Queue[TelegramUpdate] = asyncio.Queue()
        self.monitored_ids: set[int] = set()
        self.monitored_entities: dict[int, object] = {}

    async def connect(self) -> None:
        await self.client.connect()

    async def discover_pinned(self) -> list[PinnedDialog]:
        dialogs: list[PinnedDialog] = []
        entities: dict[int, object] = {}
        async for dialog in self.client.iter_dialogs():
            entity = dialog.entity
            peer_id = int(getattr(entity, "id", 0))
            entities[peer_id] = entity
            dialogs.append(PinnedDialog(
                peer_id=peer_id,
                title=str(getattr(dialog, "name", "")),
                is_channel=bool(getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False)),
                pinned=bool(getattr(dialog, "pinned", False)),
            ))
        selected = select_monitored_channels(dialogs, self.disabled)
        self.monitored_ids = {item.peer_id for item in selected}
        selected_ids = self.monitored_ids
        self.monitored_entities = {peer_id: entities[peer_id] for peer_id in selected_ids}
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
            channel_id = normalize_peer_id(int(getattr(event, "chat_id", 0) or 0))
            if channel_id not in self.monitored_ids:
                return
            for message_id in event.deleted_ids:
                await self.queue.put(TelegramUpdate("deleted", channel_id, int(message_id), None, datetime.now(tz=UTC)))

    async def _enqueue_message(self, kind: str, event) -> None:
        channel_id = normalize_peer_id(int(getattr(event, "chat_id", 0) or 0))
        if channel_id not in self.monitored_ids:
            return
        message = event.message
        observed = datetime.now(tz=UTC)
        await self.queue.put(TelegramUpdate(
            kind=kind,
            channel_id=channel_id,
            message_id=int(message.id),
            text=str(message.message or ""),
            observed_at=observed,
            published_at=getattr(message, "date", None),
            edited_at=getattr(message, "edit_date", None),
        ))

    async def backfill_recent(self, last_message_ids: dict[int, int], *, initial_limit: int = 20) -> None:
        """Recover messages that arrived while the desktop app was offline.

        Storage-level version hashes make the overlap with live updates idempotent.
        """
        for channel_id, entity in self.monitored_entities.items():
            last_message_id = last_message_ids.get(channel_id, 0)
            kwargs = (
                {"min_id": max(0, last_message_id - 100), "reverse": True, "limit": None}
                if last_message_id
                else {"limit": initial_limit}
            )
            async for message in self.client.iter_messages(entity, **kwargs):
                text = str(getattr(message, "message", "") or "")
                if not text:
                    continue
                await self.queue.put(TelegramUpdate(
                    kind="backfill",
                    channel_id=channel_id,
                    message_id=int(message.id),
                    text=text,
                    observed_at=datetime.now(tz=UTC),
                    published_at=getattr(message, "date", None),
                    edited_at=getattr(message, "edit_date", None),
                ))

    async def events(self) -> AsyncIterator[TelegramUpdate]:
        while True:
            yield await self.queue.get()

    def export_session(self) -> str:
        return self.client.session.save()

    async def disconnect(self) -> None:
        await self.client.disconnect()

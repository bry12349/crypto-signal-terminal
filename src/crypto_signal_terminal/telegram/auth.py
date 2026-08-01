from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from typing import Any, Callable

import qrcode
import qrcode.image.svg
from telethon import TelegramClient
from telethon.sessions import StringSession

from crypto_signal_terminal.config import SecretStore


def render_qr_data_uri(value: str) -> str:
    image = qrcode.make(value, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    target = BytesIO()
    image.save(target)
    encoded = base64.b64encode(target.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


class TelegramLoginManager:
    """Owns one short-lived local QR authorization flow.

    API credentials and the resulting StringSession stay in the configured
    SecretStore. The browser receives only Telegram's expiring QR token.
    """

    def __init__(
        self,
        secrets: SecretStore,
        *,
        client_factory: Callable[..., Any] = TelegramClient,
        qr_renderer: Callable[[str], str] = render_qr_data_uri,
    ) -> None:
        self.secrets = secrets
        self.client_factory = client_factory
        self.qr_renderer = qr_renderer
        self._status = "idle"
        self._qr_image: str | None = None
        self._error: str | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> dict[str, str | None]:
        if self._task and not self._task.done():
            return self.status()
        api_id = self.secrets.get("telegram_api_id")
        api_hash = self.secrets.get("telegram_api_hash")
        if not api_id or not api_hash:
            raise ValueError("telegram_credentials_missing")

        client = self.client_factory(StringSession(), int(api_id), api_hash)
        await client.connect()
        if await client.is_user_authorized():
            self.secrets.set("telegram_session", client.session.save())
            await client.disconnect()
            self._status = "authorized"
            self._qr_image = None
            return self.status()

        qr_login = await client.qr_login()
        self._status = "waiting_scan"
        self._error = None
        self._qr_image = self.qr_renderer(qr_login.url)
        self._task = asyncio.create_task(self._complete(qr_login, client))
        return self.status()

    async def _complete(self, qr_login: Any, client: Any) -> None:
        try:
            await qr_login.wait(timeout=120)
            self.secrets.set("telegram_session", client.session.save())
            self._status = "authorized"
            self._qr_image = None
        except asyncio.TimeoutError:
            self._status = "expired"
            self._qr_image = None
        except Exception as exc:
            self._status = "error"
            self._error = type(exc).__name__
            self._qr_image = None
        finally:
            await client.disconnect()

    async def wait(self) -> None:
        if self._task:
            await self._task

    def status(self) -> dict[str, str | None]:
        return {"status": self._status, "qr_image": self._qr_image, "error": self._error}

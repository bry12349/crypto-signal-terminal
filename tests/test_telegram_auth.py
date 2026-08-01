import asyncio

from crypto_signal_terminal.config import MemorySecretStore
from crypto_signal_terminal.telegram.auth import TelegramLoginManager


class FakeSession:
    def save(self) -> str:
        return "authorized-session"


class FakeQr:
    url = "tg://login?token=test-token"

    async def wait(self, timeout: int) -> None:
        assert timeout == 120


class FakeClient:
    session = FakeSession()

    async def connect(self) -> None: pass
    async def is_user_authorized(self) -> bool: return False
    async def qr_login(self) -> FakeQr: return FakeQr()
    async def disconnect(self) -> None: pass


def test_qr_login_saves_only_session_after_authorization() -> None:
    async def scenario() -> None:
        secrets = MemorySecretStore()
        secrets.set("telegram_api_id", "123")
        secrets.set("telegram_api_hash", "secret-hash")
        manager = TelegramLoginManager(
            secrets,
            client_factory=lambda *_: FakeClient(),
            qr_renderer=lambda value: f"data:image/svg+xml;base64,{value[-10:]}",
        )

        started = await manager.start()
        assert started["status"] == "waiting_scan"
        assert started["qr_image"].startswith("data:image/svg+xml;base64,")
        await asyncio.wait_for(manager.wait(), timeout=1)
        assert manager.status()["status"] == "authorized"
        assert secrets.get("telegram_session") == "authorized-session"
        assert "secret-hash" not in str(started)

    asyncio.run(scenario())

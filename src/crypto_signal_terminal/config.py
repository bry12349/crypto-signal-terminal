from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import keyring


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...


class KeyringSecretStore:
    service_name = "local.a0000.crypto-signal-terminal"

    def get(self, name: str) -> str | None:
        return keyring.get_password(self.service_name, name)

    def set(self, name: str, value: str) -> None:
        keyring.set_password(self.service_name, name, value)


class MemorySecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:
        self.values[name] = value


@dataclass(frozen=True)
class Settings:
    mode: str
    runtime_dir: Path
    telegram_api_id: int | None
    telegram_api_hash: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    dune_api_key: str | None
    dune_query_id: int | None

    @classmethod
    def from_environment(cls, secret_store: SecretStore | None = None) -> Settings:
        secrets = secret_store

        def text(name: str, secret_name: str) -> str | None:
            return os.getenv(name) or (secrets.get(secret_name) if secrets else None)

        def integer(name: str) -> int | None:
            secret_name = name.lower()
            raw = os.getenv(name) or (secrets.get(secret_name) if secrets else None)
            return int(raw) if raw else None

        return cls(
            mode=os.getenv("CST_MODE", "live"),
            runtime_dir=Path(os.getenv("CST_RUNTIME_DIR", str(Path.home() / ".crypto-signal-terminal"))),
            telegram_api_id=integer("TELEGRAM_API_ID"),
            telegram_api_hash=text("TELEGRAM_API_HASH", "telegram_api_hash"),
            telegram_bot_token=text("TELEGRAM_BOT_TOKEN", "telegram_bot_token"),
            telegram_chat_id=text("TELEGRAM_CHAT_ID", "telegram_chat_id"),
            dune_api_key=text("DUNE_API_KEY", "dune_api_key"),
            dune_query_id=integer("DUNE_QUERY_ID"),
        )

    def credential_status(self) -> dict[str, bool]:
        return {
            "telegram": bool(self.telegram_api_id and self.telegram_api_hash),
            "bot": bool(self.telegram_bot_token and self.telegram_chat_id),
            "dune": bool(self.dune_api_key and self.dune_query_id),
        }

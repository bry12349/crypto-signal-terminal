from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx

from crypto_signal_terminal.engines.smart_money import WalletObservation


class DuneConfigurationError(RuntimeError):
    pass


class DuneAdapter:
    def __init__(self, *, api_key: str | None, query_id: int | None, client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key
        self.query_id = query_id
        self.client = client

    def parse_rows(self, rows: list[dict]) -> list[WalletObservation]:
        parsed: list[WalletObservation] = []
        required = {"wallet", "chain", "token", "side", "value_usd", "timestamp", "tx_hash", "realized_return", "max_drawdown"}
        for row in rows:
            missing = required - row.keys()
            if missing:
                raise ValueError(f"Dune row missing fields: {', '.join(sorted(missing))}")
            timestamp = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00")).astimezone(UTC)
            parsed.append(WalletObservation(
                wallet=str(row["wallet"]),
                chain=str(row["chain"]),
                token=str(row["token"]),
                side=str(row["side"]),
                value_usd=Decimal(str(row["value_usd"])),
                timestamp=timestamp,
                tx_hash=str(row["tx_hash"]),
                realized_return=Decimal(str(row["realized_return"])),
                max_drawdown=Decimal(str(row["max_drawdown"])),
            ))
        return parsed

    async def latest_rows(self) -> list[WalletObservation]:
        if not self.api_key or not self.query_id:
            raise DuneConfigurationError("Dune smart-money provider is not configured")
        owned_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.get(
                f"https://api.dune.com/api/v1/query/{self.query_id}/results",
                headers={"X-Dune-Api-Key": self.api_key},
                params={"limit": 500},
            )
            response.raise_for_status()
            return self.parse_rows(response.json().get("result", {}).get("rows", []))
        finally:
            if owned_client:
                await client.aclose()

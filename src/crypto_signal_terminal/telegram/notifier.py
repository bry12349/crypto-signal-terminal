from __future__ import annotations

import hashlib
import html

import httpx

from crypto_signal_terminal.domain.models import ConfirmationResult
from crypto_signal_terminal.storage import AuditStore


class TelegramBotNotifier:
    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        store: AuditStore,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.store = store
        self.client = client

    async def send(self, result: ConfirmationResult) -> bool:
        key = hashlib.sha256(result.model_dump_json().encode("utf-8")).hexdigest()
        if not self.store.reserve_notification(key, result.analyzed_at):
            return False
        owned_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=10)
        try:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                data={"chat_id": self.chat_id, "text": self.format_message(result), "parse_mode": "HTML", "disable_web_page_preview": "true"},
            )
            response.raise_for_status()
            if not response.json().get("ok"):
                raise RuntimeError("Telegram Bot API rejected notification")
            return True
        except Exception:
            self.store.release_notification(key)
            raise
        finally:
            if owned_client:
                await client.aclose()

    @staticmethod
    def format_message(result: ConfirmationResult) -> str:
        signal = result.signal
        lines = [
            f"<b>{html.escape(signal.symbol or '未知币种')} {html.escape(signal.direction.value if signal.direction else '')}</b>",
            f"二次确认：<b>{result.verdict.value}</b> · 可信度 {result.confidence}",
        ]
        plan = result.order_plan
        if plan:
            lines.extend([
                "",
                f"建议：{plan.order_type.value} {plan.entry_low}-{plan.entry_high}",
                f"止损：{plan.stop}",
                f"止盈：{' / '.join(str(value) for value in plan.targets)}",
                f"净盈亏比：{plan.reward_to_risk:.2f}",
                f"有效至：{plan.expires_at.strftime('%H:%M:%S')}",
            ])
        if result.evidence:
            lines.append("")
            lines.append("依据：")
            lines.extend(f"• {html.escape(item.text)}" for item in result.evidence[:3])
        if result.reason_codes:
            lines.append("")
            lines.append("原因：" + ", ".join(html.escape(item) for item in result.reason_codes))
        return "\n".join(lines)

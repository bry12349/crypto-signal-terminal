from datetime import UTC, datetime
from decimal import Decimal

from crypto_signal_terminal.domain.models import Direction
from crypto_signal_terminal.api import ApplicationState
from crypto_signal_terminal.main import _market
from crypto_signal_terminal.storage import AuditStore
from crypto_signal_terminal.telegram.client import PinnedDialog, TelegramUpdate, select_monitored_channels
from crypto_signal_terminal.telegram.coordinator import TelegramSignalCoordinator
from crypto_signal_terminal.telegram.parser import parse_signal


NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def test_parse_chinese_signal() -> None:
    parsed = parse_signal(
        "BTC 多 68500-68700 止损 67800 止盈 70000 / 71200 杠杆 5x",
        account_id="me",
        channel_id=10,
        message_id=20,
        published_at=NOW,
    )
    assert parsed.symbol == "BTCUSDT"
    assert parsed.direction is Direction.LONG
    assert parsed.entry_low == Decimal("68500")
    assert parsed.entry_high == Decimal("68700")
    assert parsed.stop == Decimal("67800")
    assert parsed.targets == (Decimal("70000"), Decimal("71200"))
    assert parsed.leverage == Decimal("5")
    assert parsed.issues == ()


def test_parse_english_short_signal() -> None:
    parsed = parse_signal(
        "SOLUSDT SHORT entry 146.2-146.5 SL 147.4 TP 144.6 142.9",
        account_id="me",
        channel_id=10,
        message_id=21,
        published_at=NOW,
    )
    assert parsed.direction is Direction.SHORT
    assert parsed.symbol == "SOLUSDT"
    assert parsed.targets == (Decimal("144.6"), Decimal("142.9"))


def test_parser_never_guesses_missing_direction_or_entry() -> None:
    parsed = parse_signal(
        "DOGE 看起来要动了，关注一下",
        account_id="me",
        channel_id=10,
        message_id=22,
        published_at=NOW,
    )
    assert parsed.symbol == "DOGEUSDT"
    assert parsed.direction is None
    assert parsed.entry_low is None
    assert "missing_direction" in parsed.issues
    assert "missing_entry" in parsed.issues


def test_all_pinned_channels_selected_but_pinned_private_chat_ignored() -> None:
    dialogs = [
        PinnedDialog(peer_id=1, title="Alpha", is_channel=True, pinned=True),
        PinnedDialog(peer_id=2, title="Friend", is_channel=False, pinned=True),
        PinnedDialog(peer_id=3, title="Not pinned", is_channel=True, pinned=False),
    ]
    selected = select_monitored_channels(dialogs)
    assert [item.peer_id for item in selected] == [1]


def test_audit_store_deduplicates_same_version_and_keeps_edits(tmp_path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    first = store.record_message_version("me", 10, 20, "BTC long", NOW)
    duplicate = store.record_message_version("me", 10, 20, "BTC long", NOW)
    edited = store.record_message_version("me", 10, 20, "BTC long edited", NOW)
    assert first is True
    assert duplicate is False
    assert edited is True
    assert len(store.message_versions("me", 10, 20)) == 2


def test_deleted_message_retains_audit_history(tmp_path) -> None:
    store = AuditStore(tmp_path / "audit.sqlite3")
    store.record_message_version("me", 10, 20, "BTC long", NOW)
    store.mark_message_deleted("me", 10, 20, NOW)
    rows = store.message_versions("me", 10, 20)
    assert rows[-1]["deleted"] == 1


async def test_new_channel_signal_is_confirmed_and_pushed_to_phone(tmp_path) -> None:
    class Market:
        async def snapshot(self, symbol: str):
            return _market(
                symbol, "146.35", trend_1h=-1, aggressive_flow_imbalance="-0.8",
                oi_change_ratio="0.06", spread_bps="2",
            )

    class Notifier:
        sent = []
        async def send(self, result):
            self.sent.append(result)
            return True

    notifier = Notifier()
    state = ApplicationState(mode="live")
    coordinator = TelegramSignalCoordinator(
        state=state,
        store=AuditStore(tmp_path / "audit.sqlite3"),
        market=Market(),
        notifier_factory=lambda: notifier,
        clock=lambda: NOW,
    )
    update = TelegramUpdate(
        "new", 10, 21, "SOLUSDT SHORT entry 146.2-146.5 SL 147.4 TP 144.6 142.9", NOW,
    )
    result = await coordinator.process_update(update)
    assert result is not None
    assert result.signal.symbol == "SOLUSDT"
    assert state.confirmations[0].id == result.id
    assert notifier.sent == [result]

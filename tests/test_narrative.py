from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from crypto_signal_terminal.adapters.narrative import DEFAULT_SOURCES, FeedSource, PublicNarrativeClient, sources_from_environment
from crypto_signal_terminal.domain.models import NarrativeObservation
from crypto_signal_terminal.engines.narrative import NarrativeEngine


NOW = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)


def observation(
    source_id: str,
    *,
    stance: str,
    kind: str = "ANALYST",
    symbol: str = "BTCUSDT",
    published_at: datetime = NOW,
) -> NarrativeObservation:
    return NarrativeObservation(
        id=f"{source_id}:1",
        source_id=source_id,
        source_name=source_id,
        source_kind=kind,
        published_at=published_at,
        symbols=(symbol,),
        stance=Decimal(stance),
        confidence=Decimal("0.70"),
        source_prior=Decimal("0.60"),
        text="explicit market view",
    )


def test_narrative_requires_two_independent_sources_before_directional_use() -> None:
    engine = NarrativeEngine()

    one = engine.assess("BTCUSDT", (observation("analyst-a", stance="0.9"),), as_of=NOW)
    two = engine.assess(
        "BTCUSDT",
        (observation("analyst-a", stance="0.9"), observation("forum-b", stance="0.7", kind="FORUM").model_copy(update={"text": "independent upside view"})),
        as_of=NOW,
    )

    assert one.bias == "UNCONFIRMED"
    assert one.score == 0
    assert two.bias == "BULLISH"
    assert Decimal("0") < two.score <= Decimal("0.35")
    assert two.independent_sources == 2


def test_narrative_deduplicates_a_source_and_discards_stale_calls() -> None:
    engine = NarrativeEngine()
    observations = (
        observation("analyst-a", stance="0.9"),
        observation("analyst-a", stance="-0.9", published_at=NOW - timedelta(minutes=5)),
        observation("forum-b", stance="0.9", published_at=NOW - timedelta(days=2)),
    )

    result = engine.assess("BTCUSDT", observations, as_of=NOW)

    assert result.bias == "UNCONFIRMED"
    assert result.independent_sources == 1


async def test_public_feed_parser_only_emits_explicit_directional_symbol_mentions() -> None:
    xml = b"""<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns='http://www.w3.org/2005/Atom'>
      <entry><id>a</id><title>Bitcoin breakout looks bullish</title><updated>2026-09-02T07:55:00Z</updated></entry>
      <entry><id>b</id><title>General crypto discussion</title><updated>2026-09-02T07:54:00Z</updated></entry>
    </feed>"""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=xml, headers={"content-type": "application/atom+xml"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = FeedSource(
        id="analyst-a", name="Analyst A", url="https://example.test/feed",
        kind="ANALYST", prior=Decimal("0.55"),
    )
    adapter = PublicNarrativeClient(client=client, sources=(source,), refresh_seconds=0, clock=lambda: NOW)

    values = await adapter.observe(("BTCUSDT", "SOLUSDT"))

    assert len(values) == 1
    assert values[0].symbols == ("BTCUSDT",)
    assert values[0].stance > 0
    await client.aclose()


def test_malformed_custom_feed_config_falls_back_to_safe_defaults(monkeypatch) -> None:
    monkeypatch.setenv("CST_NARRATIVE_FEEDS", '[{"id":"bad","kind":"ANALYST","prior":"not-a-number"}]')
    assert sources_from_environment() == DEFAULT_SOURCES

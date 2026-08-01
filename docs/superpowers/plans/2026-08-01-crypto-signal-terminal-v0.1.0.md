# Crypto Signal Terminal v0.1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first macOS desktop MVP that finds native crypto-perpetual opportunities, discovers smart-money candidates, independently confirms Telegram channel signals, prepares paper order tickets, and pushes verdicts to the user's phone.

**Architecture:** A Python asyncio service owns all exchange, Telegram, strategy, storage, and notification behavior behind a versioned local FastAPI/WebSocket interface. A React/TypeScript interface runs in a Tauri shell and renders a three-pane Radar/Execute/Review experience. The release is runnable without credentials in deterministic demo/replay mode; live Telegram, Dune, notification, and exchange paths activate only when their local credentials are configured.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, HTTPX, websockets, Telethon, SQLite, DuckDB/Parquet, pytest, React 19, TypeScript, Vite, Zustand, Lightweight Charts 5, Tauri 2, Rust stable, PyInstaller.

## Global Constraints

- Project root is exactly `/Users/a0000/crypto-signal-terminal`.
- Do not initialize Git until all v0.1.0 acceptance checks pass.
- Do not place project artifacts under `/Users/a0000/Documents`.
- Real exchange order placement and fully automatic trading are excluded from v0.1.0.
- Missing prices, symbols, or directions are never guessed.
- LLM output cannot override deterministic freshness, liquidity, execution, or risk gates.
- No recommendation may be emitted from stale or incomplete market data.
- Telegram monitoring uses a user MTProto session; phone delivery uses a separate bot token.
- Secrets must not enter logs, crash reports, frontend state, fixtures, commits, or release artifacts.
- All strategies include realistic fees, spread, slippage, expiry, stop, targets, and invalidation.
- Smart-money labels are candidates based on evidence; a single anonymous large trade is never labeled confirmed smart money.

---

## Planned file map

### Python service

- `pyproject.toml`: Python package, dependency, pytest, and tooling configuration.
- `src/crypto_signal_terminal/domain/models.py`: versioned domain enums and immutable market/signal/order models.
- `src/crypto_signal_terminal/config.py`: local settings and credential references.
- `src/crypto_signal_terminal/market/state.py`: freshness-aware normalized market state.
- `src/crypto_signal_terminal/market/features.py`: deterministic market features.
- `src/crypto_signal_terminal/adapters/exchanges.py`: public Binance/OKX/Bybit adapter interfaces and live clients.
- `src/crypto_signal_terminal/engines/trend.py`: BTC/ETH trend lifecycle.
- `src/crypto_signal_terminal/engines/altcoin.py`: altcoin critical-state lifecycle.
- `src/crypto_signal_terminal/engines/smart_money.py`: derivatives-flow and on-chain wallet candidate scoring.
- `src/crypto_signal_terminal/adapters/dune.py`: optional Dune on-chain result adapter.
- `src/crypto_signal_terminal/telegram/parser.py`: deterministic text/caption parsing.
- `src/crypto_signal_terminal/telegram/client.py`: pinned-channel discovery and update handling.
- `src/crypto_signal_terminal/telegram/notifier.py`: Telegram Bot API mobile delivery.
- `src/crypto_signal_terminal/confirmation.py`: independent Telegram-signal verdict pipeline.
- `src/crypto_signal_terminal/order_planner.py`: market/limit choice, risk sizing, stops, targets, and expiry.
- `src/crypto_signal_terminal/storage.py`: SQLite audit records and replay-safe idempotency.
- `src/crypto_signal_terminal/api.py`: FastAPI HTTP and WebSocket contract.
- `src/crypto_signal_terminal/main.py`: process lifecycle and demo/live composition.

### Desktop

- `desktop/package.json`: frontend and Tauri dependencies/scripts.
- `desktop/src/types.ts`: TypeScript mirror of API DTOs.
- `desktop/src/store.ts`: WebSocket snapshot/event state.
- `desktop/src/App.tsx`: shell and primary navigation.
- `desktop/src/components/StatusStrip.tsx`: market/data health strip.
- `desktop/src/components/OpportunityStream.tsx`: lifecycle-sorted opportunity list.
- `desktop/src/components/SignalCanvas.tsx`: chart, structure, and evidence.
- `desktop/src/components/OrderTicket.tsx`: execution recommendation.
- `desktop/src/components/TelegramOnboarding.tsx`: local Telegram/bot credential setup.
- `desktop/src/styles.css`: graphite visual system and motion.
- `desktop/src-tauri/tauri.conf.json`: macOS application and sidecar configuration.
- `desktop/src-tauri/src/lib.rs`: sidecar lifecycle.

### Tests, fixtures, and scripts

- `tests/fixtures/*.json`: redacted market, Telegram, Dune, and replay inputs.
- `tests/test_*.py`: unit and integration coverage.
- `desktop/src/*.test.tsx`: component and store coverage.
- `scripts/bootstrap.sh`: install Rust, Python, and Node dependencies without writing secrets.
- `scripts/run-demo.sh`: start deterministic demo mode.
- `scripts/build-release.sh`: build Python sidecar and signed-off local macOS artifact.
- `.gitignore`: secrets, sessions, databases, environments, builds, and local credentials.
- `README.md`: setup, demo, live onboarding, privacy, and release instructions.

---

### Task 1: Bootstrap and immutable domain contract

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/crypto_signal_terminal/__init__.py`
- Create: `src/crypto_signal_terminal/domain/models.py`
- Create: `tests/test_domain_models.py`
- Create: `scripts/bootstrap.sh`

**Interfaces:**
- Produces: `MarketSnapshot`, `Opportunity`, `OrderPlan`, `TelegramSignal`, `SmartMoneyCandidate`, `Verdict`, `LifecycleState`, and `DataHealth`.
- All later Python tasks import these definitions and may not create parallel DTOs.

- [ ] **Step 1: Write domain validation tests**

```python
def test_actionable_opportunity_requires_order_plan():
    with pytest.raises(ValidationError):
        Opportunity(symbol="BTCUSDT", state=LifecycleState.ENTRY_VALID, evidence=[])

def test_order_plan_rejects_non_positive_reward_to_risk():
    with pytest.raises(ValidationError):
        OrderPlan(direction="LONG", entry_low=100, entry_high=100, stop=101, targets=[99])
```

- [ ] **Step 2: Run the tests and verify collection or import failure**

Run: `./.venv/bin/python -m pytest tests/test_domain_models.py -q`

Expected: failure because `crypto_signal_terminal.domain.models` does not exist.

- [ ] **Step 3: Implement Pydantic enums and frozen models**

Implement literal lifecycle transitions, UTC-aware timestamps, decimal price fields, bounded confidence, evidence records, source identity, and validators that require complete plans only for actionable states.

```python
class LifecycleState(StrEnum):
    FORMING = "FORMING"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    ENTRY_VALID = "ENTRY_VALID"
    MANAGING = "MANAGING"
    CLOSED = "CLOSED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"

class Verdict(StrEnum):
    CONFIRMED = "CONFIRMED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNPARSEABLE = "UNPARSEABLE"
```

- [ ] **Step 4: Add safe dependency bootstrap**

`scripts/bootstrap.sh` creates `.venv`, installs the locked Python package and desktop dependencies, and installs Rust through rustup only when `cargo` is absent. It must use absolute project-relative paths and `set -euo pipefail`.

- [ ] **Step 5: Run the domain tests**

Run: `./.venv/bin/python -m pytest tests/test_domain_models.py -q`

Expected: all domain tests pass.

- [ ] **Step 6: Record checkpoint without Git**

Run: `./.venv/bin/python -m pytest tests/test_domain_models.py -q && test ! -d .git`

Expected: tests pass and `.git` remains absent.

### Task 2: Freshness-aware market state and exchange normalization

**Files:**
- Create: `src/crypto_signal_terminal/market/state.py`
- Create: `src/crypto_signal_terminal/market/features.py`
- Create: `src/crypto_signal_terminal/adapters/exchanges.py`
- Create: `tests/fixtures/market_events.json`
- Create: `tests/test_market_state.py`
- Create: `tests/test_exchange_adapters.py`

**Interfaces:**
- Consumes: `MarketSnapshot`, `DataHealth`.
- Produces: `MarketState.apply(event)`, `MarketState.snapshot(symbol, now)`, `FeatureSet`, and `ExchangeAdapter.events()`.

- [ ] **Step 1: Write tests for sequence gaps, stale data, and symbol normalization**

```python
def test_sequence_gap_marks_book_unhealthy():
    state.apply(book_event(sequence=10))
    state.apply(book_event(sequence=12))
    assert state.health("BTCUSDT").book_ok is False

def test_snapshot_rejects_stale_trade_data():
    with pytest.raises(StaleMarketData):
        state.snapshot("BTCUSDT", now=event_time + timedelta(seconds=6))
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `./.venv/bin/python -m pytest tests/test_market_state.py tests/test_exchange_adapters.py -q`

Expected: import failures for the new modules.

- [ ] **Step 3: Implement normalized events and market state**

Use exchange aliases to produce canonical `BASEQUOTE` perpetual symbols, Decimal prices/sizes, exchange and receipt timestamps, and sequence-aware books. Feature calculation returns spread bps, depth imbalance, aggressive-flow imbalance, OI velocity, CVD, ATR percentile, and volume acceleration.

- [ ] **Step 4: Implement live public adapters with fixture-driven decoders**

Each adapter exposes:

```python
class ExchangeAdapter(Protocol):
    name: str
    async def events(self, symbols: Sequence[str]) -> AsyncIterator[MarketEvent]: ...
    async def snapshot(self, symbol: str) -> Sequence[MarketEvent]: ...
```

Decoder tests use redacted captured messages. Network connection tests are marked `live` and excluded from the default suite.

- [ ] **Step 5: Run market tests**

Run: `./.venv/bin/python -m pytest tests/test_market_state.py tests/test_exchange_adapters.py -q`

Expected: all tests pass.

### Task 3: Trend and altcoin opportunity engines

**Files:**
- Create: `src/crypto_signal_terminal/engines/trend.py`
- Create: `src/crypto_signal_terminal/engines/altcoin.py`
- Create: `tests/test_trend_engine.py`
- Create: `tests/test_altcoin_engine.py`

**Interfaces:**
- Consumes: `MarketSnapshot`, `FeatureSet`.
- Produces: `TrendEngine.evaluate(snapshot) -> Opportunity` and `AltcoinEngine.evaluate(snapshot) -> Opportunity | None`.

- [ ] **Step 1: Write lifecycle tests**

```python
def test_trend_pullback_is_conditional_not_market_entry():
    result = engine.evaluate(bullish_snapshot(price_above_vwap=True, pullback_active=True))
    assert result.state is LifecycleState.ARMED
    assert result.order_plan.entry_type == "LIMIT"

def test_altcoin_needs_trigger_after_compression():
    forming = engine.evaluate(compressed_snapshot(triggered=False))
    triggered = engine.evaluate(compressed_snapshot(triggered=True))
    assert forming.state is LifecycleState.FORMING
    assert triggered.state is LifecycleState.TRIGGERED
```

- [ ] **Step 2: Verify tests fail**

Run: `./.venv/bin/python -m pytest tests/test_trend_engine.py tests/test_altcoin_engine.py -q`

Expected: import failures.

- [ ] **Step 3: Implement explicit gates and evidence**

Trend gates: healthy data, 4h/1h direction agreement, 15m setup, 5m trigger, execution feasibility, and event veto. Altcoin gates: universe liquidity, compression, pre-trigger anomaly, trigger, cross-exchange confirmation, and execution feasibility.

- [ ] **Step 4: Run tests including contradictory evidence cases**

Run: `./.venv/bin/python -m pytest tests/test_trend_engine.py tests/test_altcoin_engine.py -q`

Expected: all tests pass and no test depends on an LLM.

### Task 4: Smart-money candidate engine

**Files:**
- Create: `src/crypto_signal_terminal/engines/smart_money.py`
- Create: `src/crypto_signal_terminal/adapters/dune.py`
- Create: `tests/fixtures/dune_rows.json`
- Create: `tests/test_smart_money_engine.py`
- Create: `tests/test_dune_adapter.py`

**Interfaces:**
- Consumes: `MarketSnapshot`, `FeatureSet`, optional `OnchainWalletObservation` rows.
- Produces: `SmartMoneyEngine.evaluate_flow(snapshot) -> SmartMoneyCandidate | None`, `score_wallet(history, as_of)`, and `DuneAdapter.latest_rows()`.

- [ ] **Step 1: Write no-look-ahead and anti-whale-label tests**

```python
def test_single_large_trade_is_not_smart_money():
    assert engine.evaluate_flow(snapshot_with_one_whale_print()) is None

def test_wallet_score_ignores_outcomes_after_as_of():
    early = score_wallet(history_with_future_winner(), as_of=T0)
    late = score_wallet(history_with_future_winner(), as_of=T1)
    assert late.score > early.score
```

- [ ] **Step 2: Verify tests fail**

Run: `./.venv/bin/python -m pytest tests/test_smart_money_engine.py tests/test_dune_adapter.py -q`

Expected: import failures.

- [ ] **Step 3: Implement derivatives-flow persistence scoring**

Require repeated large aggressive flow, consistent direction, OI participation, measurable price impact or absorption, and at least two time windows. Output accumulation, distribution, large-flow, or invalidated candidate with evidence.

- [ ] **Step 4: Implement optional Dune result adapter**

The adapter reads `DUNE_API_KEY` from the backend credential provider, calls a configured query result endpoint, and validates exact row fields. It disables itself with a typed health state when no key/query ID is configured.

- [ ] **Step 5: Run smart-money tests**

Run: `./.venv/bin/python -m pytest tests/test_smart_money_engine.py tests/test_dune_adapter.py -q`

Expected: all tests pass without a Dune key.

### Task 5: Telegram parsing, monitoring, and audit

**Files:**
- Create: `src/crypto_signal_terminal/telegram/parser.py`
- Create: `src/crypto_signal_terminal/telegram/client.py`
- Create: `src/crypto_signal_terminal/storage.py`
- Create: `tests/fixtures/telegram_messages.json`
- Create: `tests/test_telegram_parser.py`
- Create: `tests/test_telegram_client.py`
- Create: `tests/test_storage.py`

**Interfaces:**
- Consumes: Telegram updates.
- Produces: `parse_signal(text, published_at) -> TelegramSignal`, `PinnedChannelMonitor.events()`, and `AuditStore.record_message_version(...)`.

- [ ] **Step 1: Write Chinese/English parser and idempotency tests**

```python
@pytest.mark.parametrize("text,symbol,direction", [
    ("BTC 多 68500-68700 止损 67800 止盈 70000/71200", "BTCUSDT", "LONG"),
    ("SOL short entry 146.2-146.5 sl 147.4 tp 144.6 142.9", "SOLUSDT", "SHORT"),
])
def test_parse_common_signal(text, symbol, direction):
    parsed = parse_signal(text, published_at=NOW)
    assert (parsed.symbol, parsed.direction) == (symbol, direction)
```

- [ ] **Step 2: Verify tests fail**

Run: `./.venv/bin/python -m pytest tests/test_telegram_parser.py tests/test_telegram_client.py tests/test_storage.py -q`

Expected: import failures.

- [ ] **Step 3: Implement deterministic parser**

Normalize full-width punctuation, Chinese long/short terms, entry ranges, stop aliases, numbered targets, leverage, and quote currency. Ambiguity returns parse issues and never fills invented values.

- [ ] **Step 4: Implement Telethon monitor**

Use user authorization, fetch pinned dialogs for the main folder, enable all channel peers by default, subscribe to new/edit/delete updates, persist update state, and recover gaps before emitting recommendations. Provide a fake client for tests.

- [ ] **Step 5: Implement immutable SQLite audit versions**

Use unique `(account_id, channel_id, message_id, version_hash)` and store redacted analysis metadata separately from encrypted raw content.

- [ ] **Step 6: Run Telegram/storage tests**

Run: `./.venv/bin/python -m pytest tests/test_telegram_parser.py tests/test_telegram_client.py tests/test_storage.py -q`

Expected: all tests pass.

### Task 6: Independent confirmation, order planning, and phone delivery

**Files:**
- Create: `src/crypto_signal_terminal/order_planner.py`
- Create: `src/crypto_signal_terminal/confirmation.py`
- Create: `src/crypto_signal_terminal/telegram/notifier.py`
- Create: `tests/test_order_planner.py`
- Create: `tests/test_confirmation.py`
- Create: `tests/test_notifier.py`

**Interfaces:**
- Consumes: parsed `TelegramSignal`, `MarketSnapshot`, matching native opportunity, source profile, and user risk settings.
- Produces: `OrderPlanner.plan(...) -> OrderPlan`, `ConfirmationEngine.confirm(...) -> ConfirmationResult`, and `Notifier.send(result)`.

- [ ] **Step 1: Write order safety and verdict tests**

```python
def test_chased_signal_becomes_expired():
    result = engine.confirm(signal(entry_high=100), market(price=104, atr=1))
    assert result.verdict is Verdict.EXPIRED

def test_stale_market_cannot_confirm():
    result = engine.confirm(valid_signal(), stale_market())
    assert result.verdict is Verdict.REJECTED
    assert "stale" in result.reason_codes
```

- [ ] **Step 2: Verify tests fail**

Run: `./.venv/bin/python -m pytest tests/test_order_planner.py tests/test_confirmation.py tests/test_notifier.py -q`

Expected: import failures.

- [ ] **Step 3: Implement deterministic order planner**

Choose market only for triggered, time-sensitive, low-slippage setups. Prefer limit for pullbacks/retests. Calculate size from risk budget and total per-unit loss, validate stop direction, produce tiered targets, and add TTL.

- [ ] **Step 4: Implement verdict pipeline**

Apply parse, freshness, tradability, execution, structural alignment, price/OI/flow, cross-exchange, stop/target, net reward-to-risk, and source-history checks in order. Hard vetoes run before any weighted evidence.

- [ ] **Step 5: Implement bot notifier with idempotency key**

Send compact Chinese HTML messages through the Telegram Bot API. A deterministic result hash prevents retries from duplicating a recommendation.

- [ ] **Step 6: Run confirmation tests**

Run: `./.venv/bin/python -m pytest tests/test_order_planner.py tests/test_confirmation.py tests/test_notifier.py -q`

Expected: all tests pass with HTTP calls mocked.

### Task 7: Local API and deterministic demo composition

**Files:**
- Create: `src/crypto_signal_terminal/config.py`
- Create: `src/crypto_signal_terminal/api.py`
- Create: `src/crypto_signal_terminal/main.py`
- Create: `tests/test_api.py`
- Create: `tests/test_replay.py`
- Create: `tests/fixtures/demo_replay.json`
- Create: `scripts/run-demo.sh`

**Interfaces:**
- Consumes: engines, adapters, store, confirmation, notifier.
- Produces: `/api/v1/snapshot`, `/api/v1/health`, `/api/v1/settings/status`, `/api/v1/telegram/channels`, `/api/v1/paper-orders`, and `/api/v1/events` WebSocket.

- [ ] **Step 1: Write API schema and replay reproducibility tests**

```python
def test_snapshot_does_not_expose_secrets(client):
    body = client.get("/api/v1/snapshot").json()
    assert "api_hash" not in json.dumps(body).lower()

def test_same_replay_produces_same_opportunity_ids():
    assert run_replay(FIXTURE) == run_replay(FIXTURE)
```

- [ ] **Step 2: Verify tests fail**

Run: `./.venv/bin/python -m pytest tests/test_api.py tests/test_replay.py -q`

Expected: import failures.

- [ ] **Step 3: Implement local API and event hub**

Bind to `127.0.0.1` only, use versioned DTOs, cap WebSocket client queues, and send snapshot-followed-by-events. Settings endpoints expose only configured/not-configured booleans.

- [ ] **Step 4: Implement deterministic demo runner**

Replay fixture events at configurable speed and include at least one BTC trend opportunity, one altcoin trigger, one smart-money candidate, and one Telegram confirmation.

- [ ] **Step 5: Run backend suite**

Run: `./.venv/bin/python -m pytest -q`

Expected: all backend tests pass.

### Task 8: React Radar/Execute/Review interface

**Files:**
- Create: `desktop/package.json`
- Create: `desktop/tsconfig.json`
- Create: `desktop/vite.config.ts`
- Create: `desktop/index.html`
- Create: `desktop/src/main.tsx`
- Create: `desktop/src/types.ts`
- Create: `desktop/src/store.ts`
- Create: `desktop/src/App.tsx`
- Create: `desktop/src/components/StatusStrip.tsx`
- Create: `desktop/src/components/OpportunityStream.tsx`
- Create: `desktop/src/components/SignalCanvas.tsx`
- Create: `desktop/src/components/OrderTicket.tsx`
- Create: `desktop/src/components/TelegramOnboarding.tsx`
- Create: `desktop/src/styles.css`
- Create: `desktop/src/App.test.tsx`

**Interfaces:**
- Consumes: v1 snapshot and event DTOs.
- Produces: keyboard-first three-pane interface and credential-status onboarding.

- [ ] **Step 1: Write component behavior tests**

```tsx
it("sorts entry-valid Telegram confirmations ahead of forming signals", () => {
  render(<OpportunityStream items={fixtures} />);
  expect(screen.getAllByTestId("opportunity")[0]).toHaveTextContent("ENTRY VALID");
});

it("shows no opportunity without inventing a trade", () => {
  render(<SignalCanvas selected={null} />);
  expect(screen.getByText("当前无可执行机会")).toBeVisible();
});
```

- [ ] **Step 2: Verify tests fail**

Run: `cd desktop && pnpm test --run`

Expected: failures because components do not exist.

- [ ] **Step 3: Implement typed store and reconnect behavior**

Connect to the local snapshot first, then WebSocket events. Preserve selection by stable opportunity ID, reconnect with bounded backoff, and display stale connection state.

- [ ] **Step 4: Implement three-pane interface and graphite design tokens**

Render only status, opportunity lifecycle, selected evidence, and complete order contract. Add `J/K`, `Enter`, `Space`, and `Esc` keyboard behavior, stable card geometry, and reduced-motion support.

- [ ] **Step 5: Run frontend tests and production build**

Run: `cd desktop && pnpm test --run && pnpm build`

Expected: tests pass and `desktop/dist` is produced.

### Task 9: Tauri shell, Python sidecar, and macOS artifact

**Files:**
- Create: `desktop/src-tauri/Cargo.toml`
- Create: `desktop/src-tauri/build.rs`
- Create: `desktop/src-tauri/tauri.conf.json`
- Create: `desktop/src-tauri/capabilities/default.json`
- Create: `desktop/src-tauri/src/lib.rs`
- Create: `desktop/src-tauri/src/main.rs`
- Create: `scripts/build-release.sh`

**Interfaces:**
- Consumes: frontend build and PyInstaller service binary.
- Produces: a macOS `.app` and `.dmg` in `release/v0.1.0`.

- [ ] **Step 1: Scaffold Tauri and sidecar capability**

Configure product name `Crypto Signal Terminal`, identifier `local.a0000.crypto-signal-terminal`, localhost API allowlist, and external binary `crypto-signal-service`.

- [ ] **Step 2: Implement sidecar lifecycle**

Start the service once at application setup, pass `--port 8765`, terminate it on application exit, and show a recoverable error when startup fails. Never pass secrets on the process command line.

- [ ] **Step 3: Build the Python sidecar**

Run PyInstaller from `.venv`, name the binary with Tauri's target triple suffix, and copy it into `desktop/src-tauri/binaries`.

- [ ] **Step 4: Build and smoke-test the app**

Run: `cd desktop && pnpm tauri build`

Expected: macOS bundle and DMG are produced; launching the app shows demo mode when credentials are absent.

### Task 10: Adversarial verification, documentation, Git initialization, and v0.1.0 release

**Files:**
- Create: `README.md`
- Create: `SECURITY.md`
- Create: `tests/test_secret_redaction.py`
- Create: `tests/test_end_to_end.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: complete application.
- Produces: verified local release, initial Git commit, annotated tag, and checksums.

- [ ] **Step 1: Add adversarial tests**

Cover stale feeds, exchange sequence gaps, Telegram duplicates/edits/deletes, malformed messages, symbol ambiguity, extreme spread, negative reward-to-risk, notification retry, clock skew, secret redaction, and deterministic replay.

- [ ] **Step 2: Run all automated verification**

Run:

```bash
./.venv/bin/python -m pytest -q
cd desktop && pnpm test --run && pnpm build
cd .. && ./scripts/build-release.sh
```

Expected: all tests pass and release artifacts exist.

- [ ] **Step 3: Run live public-data smoke tests**

Connect read-only to each configured public exchange endpoint, verify timestamp freshness and symbol decoding, then disconnect. Telegram/Dune/Bot smokes are skipped with explicit status when credentials are not configured.

- [ ] **Step 4: Scan the release tree for secrets and unsafe files**

Run credential-pattern, session-file, SQLite, environment-file, and absolute-development-path scans. Expected: no secrets or private runtime data in tracked/release candidates.

- [ ] **Step 5: Initialize Git only now**

```bash
git init
git add .
git status --short
git commit -m "feat: release crypto signal terminal v0.1.0"
git tag -a v0.1.0 -m "Crypto Signal Terminal v0.1.0"
```

Expected: one intentional initial commit and annotated `v0.1.0` tag.

- [ ] **Step 6: Produce checksums and final release report**

Create SHA-256 checksums for the DMG, app archive, and source archive. Record exact test counts, live-smoke status, optional integrations not configured, commit ID, and tag.

---

## Plan self-review result

- Spec coverage: native trend, altcoin critical state, smart-money candidates, Telegram monitoring, confirmation, order planning, UI, security, tests, packaging, and deferred Git are mapped to tasks.
- Scope boundary: real order placement, automatic trading, cloud credential hosting, and broad news aggregation remain excluded.
- Placeholder scan: no implementation placeholders or unresolved requirements remain.
- Type consistency: later tasks consume the domain models and service contracts defined in Tasks 1 and 7.
- Credential boundary: demo and default tests require no secret; live integrations degrade explicitly when unconfigured.

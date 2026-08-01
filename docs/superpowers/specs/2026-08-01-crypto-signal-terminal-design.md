# Crypto Signal Terminal - Design Specification

Date: 2026-08-01
Status: Design candidate for user review
Target release: v0.1.0 local-first desktop MVP

## 1. Product definition

Crypto Signal Terminal is a local-first desktop decision terminal for intraday cryptocurrency perpetual-contract trading. It does not aggregate general financial information. It continuously filters the market and presents only actionable opportunities, their evidence, execution parameters, invalidation conditions, and remaining validity.

The product has three signal paths:

1. BTC/ETH intraday trend-following opportunities.
2. Altcoin pre-breakout and pre-breakdown critical-state opportunities.
3. Smart-money candidate discovery from derivatives flow and optional on-chain wallet data.
4. Telegram community signals that require immediate independent confirmation.

The application may recommend market or limit orders, but v0.1.0 does not place real orders. It prepares a complete order ticket for confirmation and supports paper execution. Real trading is a later, separately gated capability.

## 2. Product principles

- No information is shown unless it can affect entry, exit, sizing, or risk.
- "No trade" is a valid and common conclusion.
- The signal engine is deterministic and testable. An LLM may parse or explain a signal but may not invent market facts or override hard risk gates.
- Every recommendation includes entry, stop, targets, invalidation, expiry, estimated slippage, and evidence.
- Stale or incomplete data disables recommendations.
- BTC/ETH and altcoins use separate models and thresholds.
- Telegram content is processed locally. The application does not republish raw private-channel content.

## 3. Supported trading workflows

### 3.1 BTC/ETH intraday trend following

The engine uses 4h for directional regime, 1h for intraday structure, 15m for setup formation, and 5m for execution trigger.

Primary inputs:

- Market structure: higher highs/lows, lower highs/lows, break of structure, failed break.
- Daily and weekly open, previous-day high/low, session VWAP, recent structural levels, and volume-profile zones.
- Price/open-interest relationship.
- Aggressive buy/sell flow and cumulative volume delta.
- Pullback depth, pullback volume, breakout volume, and volatility expansion.
- Spread, visible depth, estimated slippage, and nearby liquidity.
- Extreme funding/crowding and scheduled high-impact macro-event risk as veto filters.

Possible conclusions:

- Trend long now.
- Trend short now.
- Wait for pullback to a specified zone.
- Wait for breakout confirmation at a specified trigger.
- Do not trade.

### 3.2 Altcoin critical-state detection

The altcoin universe is dynamic and limited to sufficiently liquid USDT perpetual contracts. A contract is excluded when spread, depth, listing age, data quality, or recent discontinuities fail configurable minimums.

The opportunity lifecycle is:

`FORMING -> ARMED -> TRIGGERED -> ENTRY_VALID -> MANAGING -> CLOSED`

Any pre-entry state may transition to `INVALIDATED` or `EXPIRED`.

Primary inputs:

- Volatility compression percentile using ATR and range/bandwidth measures.
- Volume, trade-count, and open-interest acceleration before price expansion.
- Aggressive trade imbalance, CVD divergence, absorption, and failed auctions.
- Order-book imbalance, liquidity withdrawal, spread changes, and depth cliffs.
- Break of compression boundary, local structure, or volume-profile boundary.
- Cross-exchange confirmation of price, trades, and open-interest changes.
- Funding/crowding, recent liquidations, and potential liquidation-chain path.
- Execution feasibility after fees and expected slippage.

An early anomaly may only enter `FORMING`. A trade recommendation requires a defined trigger and confirmation; unusual volume alone is insufficient.

### 3.3 Smart-money candidate discovery

The product distinguishes observable smart-money evidence from anonymous large trades. It never labels a single whale print as confirmed smart money.

The v0.1.0 engine has two layers:

- Derivatives-flow candidates: persistent large aggressive trades, absorption, open-interest acceleration, price impact, and cross-exchange agreement. This layer works from public exchange data without an additional provider key.
- On-chain wallet candidates: optional rows supplied by a versioned on-chain provider adapter. The first adapter accepts Dune query results with wallet, chain, token, side, value, timestamp, transaction hash, and realized-performance fields.

A wallet candidate score uses observation count, realized hit rate, median return, drawdown, recency, consistency across tokens, and whether activity precedes rather than follows price expansion. Scores are time-aware and cannot use future data. A smart-money event can strengthen or weaken another setup but cannot bypass freshness, liquidity, or execution-risk gates.

The Radar shows only:

- Accumulation candidate.
- Distribution candidate.
- Large derivatives-flow candidate.
- On-chain wallet cluster candidate.
- Candidate invalidated.

### 3.4 Telegram community-signal confirmation

The application logs in through the Telegram user API and discovers pinned dialogs. All pinned channels are monitored by default; the user can disable individual channels without unpinning them in Telegram. Non-channel pinned chats are ignored unless explicitly enabled.

The pipeline is:

`New/edited channel message -> deduplication -> signal parsing -> freshness check -> independent market analysis -> source-history adjustment -> verdict -> mobile notification`

Supported message content in v0.1.0:

- Plain text and formatted text.
- Captions attached to images.
- Common signal images through local OCR when text/caption parsing is insufficient.
- Edited messages, with versions retained for audit.

The normalized signal record contains:

- Source channel and message identifier.
- Original and edited timestamps.
- Instrument and exchange, when specified.
- Long/short direction.
- Entry price, entry range, or trigger.
- Stop loss and one or more targets.
- Leverage, timeframe, and free-form rationale when present.
- Parse confidence and a list of missing or ambiguous fields.

Missing prices are never guessed. If direction or symbol cannot be resolved, the result is `UNPARSEABLE` and the user receives a short warning rather than an order suggestion.

Independent confirmation checks:

1. Message freshness and whether current price has already moved beyond a useful entry.
2. Contract existence, tradability, spread, depth, and estimated slippage.
3. Alignment with the BTC/ETH trend engine or altcoin critical-state engine.
4. Price/OI/volume/order-flow confirmation.
5. Cross-exchange confirmation where the contract exists on multiple venues.
6. Quality of the proposed stop and targets relative to structure and liquidity.
7. Net reward-to-risk after fees, funding, and slippage.
8. Channel-specific historical reliability for similar signals.

Telegram verdicts:

- `CONFIRMED`: conditions support an immediate executable plan.
- `CONDITIONAL`: direction is plausible, but a specified trigger or pullback is required.
- `REJECTED`: current evidence contradicts the signal or execution quality is unacceptable.
- `EXPIRED`: price has moved too far or the opportunity window has closed.
- `UNPARSEABLE`: essential signal fields are missing or ambiguous.

The application may replace community stop/target levels when market structure provides a safer plan. It always displays both the community plan and the recommended plan when they differ.

### 3.5 Source reliability profile

Each monitored channel receives an evidence-based profile calculated from signals observed after monitoring begins. The system does not fabricate past performance from unavailable history.

Metrics include:

- Parseable-signal count.
- Confirmation and rejection rates.
- Maximum favorable/adverse excursion at configured horizons.
- Target-before-stop rate.
- Median time to target or invalidation.
- Performance by instrument, direction, and setup type.
- Deletion/edit frequency after publication.
- Difference between originally published and later edited entry/stop/target values.

Source reliability modifies presentation confidence but cannot override hard liquidity, freshness, and risk vetoes.

## 4. Recommendation and order-ticket contract

Every actionable recommendation uses one schema:

- Instrument and venue.
- Direction.
- Setup type and lifecycle state.
- Market, limit, or stop-triggered entry recommendation.
- Entry value or range.
- Stop-loss order type and price.
- Ordered take-profit ladder and allocation percentages.
- Invalidation condition independent of the stop price.
- Expiry timestamp or time-to-live.
- Estimated spread, slippage, fees, and funding exposure.
- Net reward-to-risk.
- Suggested size based on the configured per-trade risk limit.
- Three strongest supporting observations.
- Strongest contradictory observation or risk.
- Data freshness and venue health.
- Calibrated historical outcome statistics for the same setup bucket.

Position size is calculated as:

`risk budget / (absolute entry-stop distance + estimated per-unit costs)`

Market entry is allowed as a recommendation only after a trigger, when the opportunity is short-lived, spread/depth are acceptable, and estimated slippage is below the configured cap. Pullback and retest setups prefer limit orders.

## 5. User interface

### 5.1 Information architecture

The desktop application has three primary destinations:

1. Radar: native opportunities and incoming Telegram signals.
2. Execute: focused chart, evidence, and prepared order ticket.
3. Review: outcomes, source reliability, and engine calibration.

Settings and data health are secondary drawers, not permanent navigation items.

### 5.2 Radar screen

The top status strip contains only:

- BTC intraday regime.
- Overall altcoin risk state.
- Volatility state.
- High-impact event proximity.
- Exchange and Telegram connection health.

The left opportunity stream merges native and Telegram opportunities but clearly labels the source. Ordering is:

1. `ENTRY_VALID`
2. `TRIGGERED`
3. Telegram messages awaiting/receiving confirmation
4. `ARMED`
5. `FORMING`

Invalidated and expired items fade into history automatically.

The center panel shows the selected instrument, key structure, trigger, entry, stop, targets, and only abnormal OI/order-flow/liquidation evidence.

The right panel shows the recommendation contract. Raw metrics are hidden behind an evidence drawer.

### 5.3 Telegram signal experience

On a new pinned-channel message:

1. A compact card appears immediately with `ANALYZING` and elapsed milliseconds/seconds.
2. Parsed fields fill in without moving the card layout.
3. The verdict replaces the analyzing state.
4. Only `CONFIRMED`, `CONDITIONAL`, or urgent `REJECTED` results create a phone notification.
5. Selecting the card opens side-by-side community and recommended plans.

Example mobile response:

```text
SOLUSDT SHORT - CONDITIONAL
Community entry: market near 146.40
Verdict: direction agrees, but do not chase.

Preferred plan
Limit: 146.70-146.95 after failed reclaim
Stop: 147.62
TP1: 145.10
TP2: 143.65
Net R:R: 2.4
Valid for: 6 minutes

Why
- 15m structure is bearish
- OI is rising with aggressive selling
- Current price is already 0.8% below the original trigger

Risk: BTC is approaching support.
```

For v0.1.0, mobile delivery uses a dedicated Telegram bot chat. Monitoring uses the user's MTProto session; notification uses the bot token. This separation prevents the notification component from reading account dialogs and produces reliable phone notifications with action buttons.

### 5.4 Visual language and motion

- Graphite-black surfaces with subtle cool-gray boundaries.
- Green and red are reserved for actionable long/short state and price changes.
- Amber is reserved for conditional or elevated-risk state.
- Monospaced numerals; high-legibility Chinese interface font.
- No decorative gradients, large shadows, or continuously flashing values.
- 120-180 ms transitions.
- Stable card geometry during live updates.
- Render updates are throttled independently of market-data ingestion to preserve smooth 60 fps interaction.
- Keyboard navigation supports opportunity selection, evidence expansion, order preparation, and dismissal.

## 6. System architecture

### 6.1 Desktop and service boundary

- Desktop shell: Tauri.
- UI: React and TypeScript.
- Charting: TradingView Lightweight Charts with locally calculated overlays.
- Local service: Python 3.12 with FastAPI and asyncio.
- Configuration and relational records: SQLite.
- Time-series research store: Parquet queried through DuckDB.
- Secret storage: macOS Keychain and Windows Credential Manager.

The UI never connects directly to exchanges or Telegram. It consumes a stable local API and event stream from the service.

### 6.2 Bounded components

- `exchange_adapters`: one adapter per exchange; emits normalized market events.
- `market_state`: maintains books, candles, trades, OI, funding, and freshness.
- `trend_engine`: BTC/ETH regime, setup, and trigger states.
- `altcoin_engine`: dynamic universe and critical-state lifecycle.
- `smart_money_engine`: derivatives-flow candidates, optional on-chain provider rows, and time-aware scoring.
- `telegram_client`: authorization, pinned-channel selection, and update recovery.
- `signal_parser`: deterministic parsing, optional OCR, and structured LLM fallback.
- `confirmation_engine`: applies market, execution, and source-history checks.
- `source_profiler`: calculates forward outcomes without look-ahead.
- `order_planner`: entry type, stops, targets, sizing, expiry, and costs.
- `notifier`: Telegram-bot phone delivery and desktop notifications.
- `audit_store`: immutable source message versions, analysis versions, and decisions.
- `desktop_api`: query and event interfaces for the UI.

Each component communicates through versioned domain events. Exchange-specific and Telegram-specific objects do not leak into signal engines.

### 6.3 Event flow and latency budget

Native market flow:

`Exchange event -> normalize -> state update -> features -> setup state -> trigger -> order plan -> UI/notification`

Telegram flow:

`Telegram update -> persist/dedupe -> parse -> fetch current market snapshot -> confirm -> order plan -> UI/phone`

Target local processing budgets, excluding upstream network latency:

- Text Telegram signal parse: p95 under 300 ms without LLM fallback.
- Deterministic confirmation after market state is available: p95 under 500 ms.
- UI event propagation: p95 under 100 ms.
- Phone notification dispatch begins within 1.5 seconds of a complete deterministic verdict.

OCR and LLM fallback are explicitly marked slower paths and may not block simpler deterministic parsing.

## 7. Telegram integration and security

Telegram's user API is required because pinned dialogs are a user-only capability. Onboarding requires a Telegram `api_id` and `api_hash`, obtained by the user from Telegram's application portal, followed by QR or phone-code authorization.

Security rules:

- Authorization codes and 2FA passwords are never logged or persisted.
- MTProto session material is encrypted at rest using an OS-keychain-managed key.
- Telegram `api_hash`, bot token, and exchange credentials never enter frontend state or logs.
- The user can revoke the session and delete local channel data from Settings.
- Channel messages are stored only as much as required for audit and source profiling; configurable retention defaults to 90 days.
- Raw private-channel content is never sent in phone notifications unless the user explicitly enables quoting.
- If optional remote LLM parsing is enabled, only the minimum required message text is sent and the UI clearly identifies that privacy boundary. Local deterministic parsing remains the default.

Telegram update sequence state is persisted. On reconnect, gaps are recovered before new recommendations are emitted, preventing missed or duplicated channel signals.

## 8. Data quality and failure behavior

- Every event has source, exchange timestamp, receipt timestamp, and sequence identifiers where available.
- Order books are rebuilt from snapshots and deltas; sequence gaps trigger a resnapshot.
- Exchange reconnect triggers bounded historical backfill before the venue becomes healthy.
- A stale market snapshot cannot confirm a Telegram signal.
- Duplicate Telegram updates are idempotent by account/channel/message/version.
- Edited signal messages produce a new analysis and disclose what changed.
- Deleted signals remain in the local audit log with a deletion marker for source-reliability analysis.
- If one venue fails, cross-exchange confirmation degrades explicitly; it never silently treats missing data as agreement.
- Notification retry is idempotent and cannot send duplicate order recommendations.
- Clock skew is measured against exchange and Telegram timestamps.

## 9. Validation and testing

### 9.1 Unit tests

- Parsers for common Chinese and English signal formats.
- Price ranges, leverage syntax, targets, stops, and ambiguous symbols.
- Lifecycle state transitions and expiry.
- Position sizing, fees, slippage, and reward-to-risk.
- Data freshness and venue-health vetoes.
- Telegram edit/delete/deduplication behavior.

### 9.2 Replay and integration tests

- Recorded exchange WebSocket snapshots and deltas, including gaps and reconnects.
- Recorded Telegram updates with redacted content.
- Deterministic end-to-end replay from message to verdict.
- Cross-exchange symbol mapping and timestamp reconciliation.
- Notification retries and duplicate suppression.

### 9.3 Strategy validation

- Time-ordered walk-forward testing with no future leakage.
- Fees, funding, spread, latency, and slippage included.
- Separate calibration for BTC/ETH and liquidity-bucketed altcoins.
- Paper-trading burn-in before any real-order capability.
- Live dashboards compare forecast buckets with realized outcomes.

### 9.4 Security tests

- Secret redaction from logs, crash reports, and frontend events.
- Session revocation and secure local deletion.
- Malformed or adversarial Telegram message content.
- Dependency and package audit before release.

## 10. v0.1.0 scope

Included:

- macOS desktop build, with cross-platform-compatible architecture.
- Binance, OKX, and Bybit public perpetual-market adapters for the selected universe.
- BTC/ETH trend engine.
- Altcoin critical-state radar with forming/armed/triggered states.
- Smart-money candidate radar using public derivatives flow plus an optional Dune-compatible on-chain adapter.
- Telegram user login, pinned-channel discovery, per-channel enablement, and live message/edit monitoring.
- Text signal parser and image-caption parsing; OCR fallback for common screenshots.
- Independent confirmation and source-performance tracking from first observation onward.
- Market/limit order recommendations and paper order tickets.
- Telegram-bot delivery to the user's phone.
- Data-health, privacy, and audit views.

Excluded from v0.1.0:

- Real exchange order placement.
- Fully automatic trading.
- Cloud-hosted Telegram session or exchange credentials.
- General news aggregation and social feeds.
- Full historical claims for Telegram channels before monitoring begins.
- Guarantees of profitability or guaranteed prediction of pumps/dumps.

## 11. Release acceptance criteria

- The application recovers Telegram and exchange connection gaps without duplicate recommendations.
- A supported text signal reaches a deterministic verdict locally within the defined latency budget when upstream data is healthy.
- Every actionable verdict contains a complete order plan and explicit invalidation/expiry.
- No actionable verdict is emitted from stale, incomplete, or insufficient-liquidity data.
- The UI remains responsive during full selected-universe ingestion.
- Secrets are absent from logs and frontend payloads.
- Recorded end-to-end replay produces reproducible verdicts.
- The initial paper-trading report includes realistic costs and separates the two strategy families.

## 12. Repository and release policy

The project lives at `/Users/a0000/crypto-signal-terminal`.

Per user instruction, the directory is not initialized as a Git repository during design or early implementation. After the v0.1.0 acceptance checks pass:

1. Initialize the Git repository.
2. Review the complete file set and secret exclusions.
3. Create the initial commit.
4. Create annotated tag `v0.1.0`.
5. Produce local release artifacts and checksums.

Publishing to a remote hosting service is a separate external action and requires a target account/repository selection at release time.

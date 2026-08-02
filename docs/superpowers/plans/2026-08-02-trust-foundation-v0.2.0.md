# Trust Foundation v0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-symbol market health, server-side tradeability checks, persistent paper-order history, and clear desktop status for v0.2.0.

**Architecture:** A focused `MarketHealthRegistry` owns per-symbol status and derives the legacy overall status. `ApplicationState`, scanners, Telegram confirmation, and the order API consume that interface. `AuditStore` remains the single local persistence boundary and adds a paper-order table.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, SQLite, pytest, React 19, TypeScript, Zustand, Vitest, Tauri 2.

## Global Constraints

- The service remains bound to `127.0.0.1`.
- No exchange credentials or real-order capability are added.
- Health errors expose only controlled categories, never upstream bodies or secrets.
- A live paper order requires symbol health observed no more than 30 seconds ago.
- Development follows test-first red-green-refactor cycles.

---

### Task 1: Per-symbol market health registry

**Files:**
- Create: `src/crypto_signal_terminal/market/health.py`
- Modify: `src/crypto_signal_terminal/api.py`
- Modify: `src/crypto_signal_terminal/market/scanner.py`
- Modify: `src/crypto_signal_terminal/telegram/coordinator.py`
- Test: `tests/test_market_health.py`
- Test: `tests/test_live_scanner.py`

**Interfaces:**
- Produces: `MarketHealthRegistry(watchlist=...)`, `record_success(snapshot)`, `record_failure(symbol, observed_at, reason)`, `overall`, `is_tradable(symbol, now, max_age_seconds=30)`, and `snapshot()`.

- [ ] Write tests proving per-symbol success/failure, freshness, overall derivation, scanner partial failure, and Telegram non-overwrite behavior.
- [ ] Run the focused tests and verify they fail for missing behavior.
- [ ] Implement the minimal registry and integrate scanner/coordinator state updates.
- [ ] Run focused and full Python tests.
- [ ] Commit the health-registry slice.

### Task 2: Persistent paper-order journal and API gate

**Files:**
- Modify: `src/crypto_signal_terminal/storage.py`
- Modify: `src/crypto_signal_terminal/api.py`
- Modify: `src/crypto_signal_terminal/main.py`
- Test: `tests/test_confirmation_and_orders.py`
- Test: `tests/test_api_and_demo.py`

**Interfaces:**
- Produces: `AuditStore.record_paper_order(record)`, `AuditStore.paper_orders(limit=50)`, `GET /api/v1/paper-orders`, and health-aware `POST /api/v1/paper-orders`.

- [ ] Write failing tests for stale/degraded rejection, successful persistence, bounded history, and restart recovery.
- [ ] Run focused tests and confirm the expected failures.
- [ ] Add the SQLite table, persistence methods, API validation, and startup wiring.
- [ ] Run focused and full Python tests.
- [ ] Commit the paper-order slice.

### Task 3: Desktop trust indicators and actionable errors

**Files:**
- Modify: `desktop/src/types.ts`
- Modify: `desktop/src/store.ts`
- Modify: `desktop/src/App.tsx`
- Modify: `desktop/src/components/StatusStrip.tsx`
- Modify: `desktop/src/components/SignalCanvas.tsx`
- Modify: `desktop/src/components/OrderTicket.tsx`
- Modify: `desktop/src/styles.css`
- Test: `desktop/src/components/SignalCanvas.test.tsx`
- Test: `desktop/src/components/OrderTicket.test.tsx`
- Test: `desktop/src/components/StatusStrip.test.tsx`

**Interfaces:**
- Consumes: health payload containing `overall`, `healthy_count`, `expected_count`, and `symbols`.
- Produces: coverage status, selected-symbol badge, and server rejection detail.

- [ ] Write failing component tests for coverage, symbol status, and rejection copy.
- [ ] Run Vitest and confirm failures.
- [ ] Extend types/store and implement the smallest UI changes that satisfy the tests.
- [ ] Run Vitest and the production frontend build.
- [ ] Commit the desktop slice.

### Task 4: Version, documentation, verification, and release

**Files:**
- Modify: `pyproject.toml`
- Modify: `desktop/package.json`
- Modify: `desktop/src-tauri/Cargo.toml`
- Modify: `desktop/src-tauri/tauri.conf.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: consistent `0.2.0` metadata and a release note with safety boundaries.

- [ ] Update all version fields and user-facing documentation.
- [ ] Run version consistency checks and scan the diff for secrets and unintended files.
- [ ] Run full Python, frontend, Rust, production-build, and live public-market smoke checks.
- [ ] Review the complete diff against the design acceptance criteria.
- [ ] Commit, create the GitHub repository, push the default branch and `v0.2.0` tag, then create the GitHub Release.

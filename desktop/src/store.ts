import { create } from "zustand";

import type { BtcCycle, Health, Opportunity, Snapshot } from "./types";

const API = "http://127.0.0.1:8765";

export function mergeSignalPaths(snapshot: Snapshot): Opportunity[] {
  const smart: Opportunity[] = snapshot.smart_money.map((item) => ({
    id: item.id,
    symbol: item.symbol,
    source: "SMART_MONEY",
    state: "ARMED",
    confidence: item.score,
    title: item.wallet ? "公开钱包追踪" : item.direction === "LONG" ? "聪明钱流入候选" : "聪明钱流出候选",
    risk: item.wallet ? "链上钱包观察不等同于 CEX 开仓；仍需行情、流动性与触发确认" : "候选行为不会绕过入场触发",
    source_label: item.chain ?? "合约订单流",
    onchain_token_address: item.token_address ?? null,
    // A wallet ranking can mention tokens that have no verified perpetual
    // market. Only chart a pair present in this snapshot; otherwise use the
    // clearly labelled BTC benchmark rather than requesting a fictitious pair.
    market_symbol: (() => {
      const candidate = `${item.symbol.replace(/USDT$/, "")}USDT`;
      return candidate in (snapshot.candles ?? {}) ? candidate : "BTCUSDT";
    })(),
    updated_at: item.observed_at,
    evidence: item.evidence,
    order_plan: null,
  }));
  return [...snapshot.opportunities, ...smart];
}

interface TerminalStore {
  snapshot: Snapshot;
  opportunities: Opportunity[];
  health: Health;
  selectedId: string | null;
  connected: boolean;
  cycle: BtcCycle | null;
  load: () => Promise<void>;
  connectEvents: () => () => void;
  select: (id: string) => void;
}

export const useTerminalStore = create<TerminalStore>((set) => ({
  snapshot: { mode: "live", opportunities: [], smart_money: [], candles: {} },
  opportunities: [],
  health: {
    mode: "demo", market: "healthy", dune: "not_configured",
    market_detail: { overall: "connecting", healthy_count: 0, expected_count: 0, symbols: {} },
  },
  selectedId: null,
  connected: false,
  cycle: null,
  select: (id) => set({ selectedId: id }),
  connectEvents: () => {
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let attempt = 0;
    let stopped = false;
    const connect = () => {
      if (stopped) return;
      socket = new WebSocket("ws://127.0.0.1:8765/api/v1/events");
      socket.onopen = () => { attempt = 0; set({ connected: true }); };
      socket.onmessage = (message) => {
        const event = JSON.parse(String(message.data)) as { type: string; payload: Snapshot };
        if (event.type !== "snapshot") return;
        const snapshot = event.payload;
        const opportunities = mergeSignalPaths(snapshot);
        set((state) => ({
          snapshot,
          opportunities,
          selectedId: opportunities.some((item) => item.id === state.selectedId) ? state.selectedId : opportunities[0]?.id ?? null,
        }));
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        set({ connected: false });
        if (stopped) return;
        const delay = Math.min(10_000, 500 * (2 ** attempt));
        attempt += 1;
        retryTimer = window.setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      stopped = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      socket?.close();
    };
  },
  load: async () => {
    try {
      const [snapshotResponse, healthResponse, cycleResponse] = await Promise.all([fetch(`${API}/api/v1/snapshot`), fetch(`${API}/api/v1/health`), fetch(`${API}/api/v1/cycle/btc`)]);
      if (!snapshotResponse.ok || !healthResponse.ok) throw new Error("local service unavailable");
      const snapshot = (await snapshotResponse.json()) as Snapshot;
      const health = (await healthResponse.json()) as Health;
      const cycle = cycleResponse.ok ? await cycleResponse.json() as BtcCycle : null;
      const opportunities = mergeSignalPaths(snapshot);
      set((state) => ({
        snapshot,
        opportunities,
        health,
        connected: true,
        cycle,
        selectedId: opportunities.some((item) => item.id === state.selectedId) ? state.selectedId : opportunities[0]?.id ?? null,
      }));
    } catch {
      set({ connected: false, opportunities: [], selectedId: null });
    }
  },
}));

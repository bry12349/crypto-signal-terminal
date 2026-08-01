import { create } from "zustand";

import type { Health, Opportunity, Snapshot } from "./types";

const API = "http://127.0.0.1:8765";

function mergeSignalPaths(snapshot: Snapshot): Opportunity[] {
  const confirmations: Opportunity[] = snapshot.confirmations.map((item) => ({
    id: item.id,
    symbol: item.signal.symbol ?? "UNKNOWN",
    source: "TELEGRAM",
    state: item.verdict === "CONFIRMED" ? "ENTRY_VALID" : item.verdict === "CONDITIONAL" ? "ARMED" : "INVALIDATED",
    confidence: item.confidence,
    title: `Telegram 二次确认 · ${item.verdict}`,
    risk: item.reason_codes.join(" · ") || null,
    source_label: `频道 ${item.signal.channel_id}`,
    updated_at: item.analyzed_at,
    evidence: item.evidence,
    order_plan: item.order_plan,
  }));
  const smart: Opportunity[] = snapshot.smart_money.map((item) => ({
    id: item.id,
    symbol: item.symbol,
    source: "SMART_MONEY",
    state: "ARMED",
    confidence: item.score,
    title: item.direction === "LONG" ? "聪明钱流入候选" : "聪明钱流出候选",
    risk: "候选行为不会绕过入场触发",
    source_label: item.chain ?? "合约订单流",
    updated_at: item.observed_at,
    evidence: item.evidence,
    order_plan: null,
  }));
  return [...snapshot.opportunities, ...confirmations, ...smart];
}

interface TerminalStore {
  snapshot: Snapshot;
  opportunities: Opportunity[];
  health: Health;
  selectedId: string | null;
  connected: boolean;
  load: () => Promise<void>;
  connectEvents: () => () => void;
  select: (id: string) => void;
}

export const useTerminalStore = create<TerminalStore>((set) => ({
  snapshot: { mode: "live", opportunities: [], smart_money: [], confirmations: [], candles: {} },
  opportunities: [],
  health: { mode: "demo", market: "healthy", telegram: "not_configured", bot: "not_configured", dune: "not_configured" },
  selectedId: null,
  connected: false,
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
      const [snapshotResponse, healthResponse] = await Promise.all([fetch(`${API}/api/v1/snapshot`), fetch(`${API}/api/v1/health`)]);
      if (!snapshotResponse.ok || !healthResponse.ok) throw new Error("local service unavailable");
      const snapshot = (await snapshotResponse.json()) as Snapshot;
      const health = (await healthResponse.json()) as Health;
      const opportunities = mergeSignalPaths(snapshot);
      set((state) => ({
        snapshot,
        opportunities,
        health,
        connected: true,
        selectedId: opportunities.some((item) => item.id === state.selectedId) ? state.selectedId : opportunities[0]?.id ?? null,
      }));
    } catch {
      set({ connected: false, opportunities: [], selectedId: null });
    }
  },
}));

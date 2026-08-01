import { create } from "zustand";

import { demoSnapshot } from "./demo";
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
  select: (id: string) => void;
}

export const useTerminalStore = create<TerminalStore>((set) => ({
  snapshot: demoSnapshot,
  opportunities: mergeSignalPaths(demoSnapshot),
  health: { mode: "demo", market: "healthy", telegram: "not_configured", bot: "not_configured", dune: "not_configured" },
  selectedId: demoSnapshot.opportunities[1]?.id ?? demoSnapshot.opportunities[0]?.id ?? null,
  connected: false,
  select: (id) => set({ selectedId: id }),
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
      set({ connected: false });
    }
  },
}));

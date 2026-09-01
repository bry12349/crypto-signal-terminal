import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OpportunityStream } from "./OpportunityStream";
import type { Opportunity } from "../types";


const items: Opportunity[] = [
  {
    id: "forming",
    symbol: "DOGEUSDT",
    source: "NATIVE",
    state: "FORMING",
    confidence: 61,
    title: "临界形成中",
    risk: null,
    source_label: null,
    updated_at: "2026-08-01T08:00:00Z",
    evidence: [],
    order_plan: null,
  },
  {
    id: "entry",
    symbol: "SOLUSDT",
    source: "NATIVE",
    state: "ENTRY_VALID",
    confidence: 84,
    title: "原生趋势确认",
    risk: "BTC approaching support",
    source_label: "Alpha Channel",
    updated_at: "2026-08-01T08:00:01Z",
    evidence: [],
    order_plan: null,
  },
];


describe("OpportunityStream", () => {
  it("sorts entry-valid confirmations ahead of forming signals", () => {
    render(<OpportunityStream items={items} selectedId={null} onSelect={() => undefined} />);
    const cards = screen.getAllByTestId("opportunity");
    expect(cards[0]).toHaveTextContent("SOL");
    expect(cards[0]).toHaveTextContent("可入场");
  });

  it("shows an explicit empty state", () => {
    render(<OpportunityStream items={[]} selectedId={null} onSelect={() => undefined} />);
    expect(screen.getByText("当前无可执行机会")).toBeVisible();
  });

  it("keeps state text in a semantic badge instead of the 6px status dot", () => {
    render(<OpportunityStream items={items} selectedId={null} onSelect={() => undefined} />);
    expect(screen.getAllByText("可入场")[0]).toHaveClass("state-label");
  });

  it("ranks positive expectancy ahead of raw confidence within the same lifecycle state", () => {
    const analysis = {
      opportunity_score: 70, confidence: 70, p_tp_before_sl: "0.60", expected_value: "0.20", evidence_conflict: "0.10", is_tradeable: true,
      market_regime: "TREND", signal_type: "trend_continuation", smart_money_bias: "UNAVAILABLE", derivatives_bias: "BULLISH", order_flow_bias: "BULLISH", news_bias: "UNAVAILABLE",
    };
    const higherEdge = { ...items[1], id: "higher-edge", symbol: "BTCUSDT", confidence: 70, analysis };
    const higherConfidence = { ...items[1], id: "higher-confidence", symbol: "ETHUSDT", confidence: 95, analysis: { ...analysis, expected_value: "0.05" } };

    const view = render(<OpportunityStream items={[higherConfidence, higherEdge]} selectedId={null} onSelect={() => undefined} />);

    expect(within(view.container).getAllByTestId("opportunity")[0]).toHaveTextContent("BTC");
  });
});

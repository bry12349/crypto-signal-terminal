import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OpportunityStream } from "./OpportunityStream";
import { demoSnapshot } from "../demo";
import type { Opportunity } from "../types";

const activePlan = {
  direction: "LONG" as const,
  order_type: "LIMIT" as const,
  entry_low: "140", entry_high: "141", stop: "138", targets: ["145", "148"], target_allocations: ["0.5", "0.5"],
  expires_at: "2099-01-01T00:00:00Z", max_slippage_bps: "8", suggested_quantity: "1", risk_amount: "25", reward_to_risk: "2",
  invalidation: "5m close below 138", estimated_fees: "1",
};

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
    order_plan: activePlan,
  },
];


describe("OpportunityStream", () => {
  afterEach(cleanup);

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

  it("offers one click navigation to the best executable signal", () => {
    const onSelect = vi.fn();
    const best = { ...items[1], analysis: {
      opportunity_score: 80, confidence: 80, p_tp_before_sl: "0.64", expected_value: "0.22", evidence_conflict: "0.10", is_tradeable: true,
      market_regime: "TREND", signal_type: "trend_continuation", smart_money_bias: "UNAVAILABLE", derivatives_bias: "BULLISH", order_flow_bias: "BULLISH", news_bias: "UNAVAILABLE",
    } };
    const view = render(<OpportunityStream items={[best, items[0]]} selectedId={null} onSelect={onSelect} />);

    fireEvent.click(within(view.container).getByRole("button", { name: "查看最佳信号" }));

    expect(onSelect).toHaveBeenCalledWith("entry");
  });

  it("does not advertise an expired plan as ready to enter", () => {
    const current = demoSnapshot.opportunities[0];
    const expired = { ...current, analysis: {
      opportunity_score: 80, confidence: 80, p_tp_before_sl: "0.64", expected_value: "0.22", evidence_conflict: "0.10", is_tradeable: true,
      market_regime: "TREND", signal_type: "trend_continuation", smart_money_bias: "UNAVAILABLE", derivatives_bias: "BULLISH", order_flow_bias: "BULLISH", news_bias: "UNAVAILABLE",
    }, order_plan: { ...current.order_plan!, expires_at: "2024-01-01T00:00:00Z" } };

    const view = render(<OpportunityStream items={[expired, items[0]]} selectedId={expired.id} onSelect={() => undefined} />);

    const cards = within(view.container).getAllByTestId("opportunity");
    expect(cards[0]).toHaveTextContent("DOGE");
    expect(cards[1]).toHaveTextContent("已过期");
    expect(screen.queryByRole("button", { name: "查看最佳信号" })).not.toBeInTheDocument();
  });

  it("keeps stock and commodity opportunities out of the altcoin filter", () => {
    const profile = (asset_profile: "ALT" | "COMMODITY" | "US_EQUITY"): Opportunity["analysis"] => ({
      opportunity_score: 50, confidence: 50, p_tp_before_sl: "0.5", expected_value: "0", evidence_conflict: "0", is_tradeable: false,
      market_regime: "RANGE", signal_type: "test", smart_money_bias: "UNAVAILABLE", derivatives_bias: "NEUTRAL", order_flow_bias: "NEUTRAL", news_bias: "UNAVAILABLE", asset_profile,
    });
    const commodity = { ...items[0], id: "commodity", symbol: "XAUUSDT", analysis: profile("COMMODITY") };
    const equity = { ...items[0], id: "equity", symbol: "AAPLUSDT", analysis: profile("US_EQUITY") };
    render(<OpportunityStream items={[items[0], commodity, equity]} selectedId={null} onSelect={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "山寨" }));
    expect(screen.getAllByTestId("opportunity")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "大宗商品" }));
    expect(screen.getAllByTestId("opportunity")[0]).toHaveTextContent("XAU");
    fireEvent.click(screen.getByRole("button", { name: "美股" }));
    expect(screen.getAllByTestId("opportunity")[0]).toHaveTextContent("AAPL");
  });
});

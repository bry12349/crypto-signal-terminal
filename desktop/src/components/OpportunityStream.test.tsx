import { render, screen } from "@testing-library/react";
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
});

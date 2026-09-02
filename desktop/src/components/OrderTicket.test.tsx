import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrderTicket } from "./OrderTicket";
import { demoSnapshot } from "../demo";


describe("OrderTicket", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("puts the complete trading decision above secondary execution details", () => {
    render(<OrderTicket opportunity={demoSnapshot.opportunities[0]} />);

    expect(screen.getByRole("heading", { name: "可以做多" })).toBeVisible();
    expect(screen.getByText("限价挂单")).toBeVisible();
    expect(screen.getByText("可靠度 83/100")).toBeVisible();
    expect(screen.getByText("入场区间")).toBeVisible();
    expect(screen.getByText("止损")).toBeVisible();
    expect(screen.getByText("止盈 1")).toBeVisible();
    expect(screen.getByRole("heading", { name: "做单理由" })).toBeVisible();
    expect(screen.getByText("4h 与 1h 多头结构一致")).toBeVisible();
  });

  it("explains at a glance why a selected setup cannot be traded", () => {
    const forming = demoSnapshot.opportunities[2];
    render(<OrderTicket opportunity={forming} />);

    expect(screen.getByRole("heading", { name: "现在不能做" })).toBeVisible();
    expect(screen.getByText("等待 1.086 放量突破")).toBeVisible();
    expect(screen.getByText("可靠度 72/100")).toBeVisible();
    expect(screen.queryByRole("button", { name: /准备模拟订单/ })).not.toBeInTheDocument();
  });

  it("keeps execution locked when analysis rejects a setup that still carries an old plan", () => {
    const request = vi.fn();
    vi.stubGlobal("fetch", request);
    render(<OrderTicket opportunity={{ ...demoSnapshot.opportunities[0], analysis: {
      opportunity_score: 35, confidence: 40, p_tp_before_sl: "0.42", expected_value: "-0.15", evidence_conflict: "0.38", is_tradeable: false,
      market_regime: "RANGE", signal_type: "none", smart_money_bias: "NEUTRAL", derivatives_bias: "NEUTRAL", order_flow_bias: "NEUTRAL", news_bias: "UNAVAILABLE",
      decision: { outcome: "NO_TRADE", gates: [{ key: "expected_value", label: "净期望值不足", passed: false, observed: "-0.15", required: "0" }] },
    } }} />);

    window.dispatchEvent(new Event("prepare-order"));
    expect(screen.getByRole("heading", { name: "现在不能做" })).toBeVisible();
    expect(request).not.toHaveBeenCalled();
  });

  it("never labels an expired execution plan as tradable", () => {
    const current = demoSnapshot.opportunities[0];
    render(<OrderTicket opportunity={{ ...current, order_plan: { ...current.order_plan!, expires_at: "2024-01-01T00:00:00Z" } }} />);

    expect(screen.getByRole("heading", { name: "现在不能做" })).toBeVisible();
    expect(screen.getByText("信号已过期，等待重新分析")).toBeVisible();
    expect(screen.queryByRole("button", { name: /准备模拟订单/ })).not.toBeInTheDocument();
  });

  it("never renders an execution button without a complete plan", () => {
    render(<OrderTicket opportunity={null} />);
    expect(screen.getByText("等待可执行结构")).toBeVisible();
    expect(screen.queryByRole("button", { name: "准备模拟订单" })).not.toBeInTheDocument();
  });

  it("prepares the selected paper order through the local API", async () => {
    const request = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", request);
    render(<OrderTicket opportunity={demoSnapshot.opportunities[0]} />);
    fireEvent.click(screen.getByRole("button", { name: /准备模拟订单/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /模拟订单已准备/ })).toBeDisabled());
    expect(request).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/v1/paper-orders",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ opportunity_id: "trend:BTCUSDT:demo" }) }),
    );
  });

  it("shows the server rejection reason instead of a generic error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: "Symbol market data is stale or unavailable" }),
    }));
    render(<OrderTicket opportunity={demoSnapshot.opportunities[0]} />);
    fireEvent.click(screen.getByRole("button", { name: /准备模拟订单/ }));
    expect(await screen.findByText("该币种行情已过期或不可用，请等待下一轮刷新")).toBeVisible();
  });
});

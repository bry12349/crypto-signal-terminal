import { fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";

const chartMock = vi.hoisted(() => ({ removed: false }));

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: {}, HistogramSeries: {}, LineSeries: {}, ColorType: { Solid: "solid" },
  createChart: () => {
    chartMock.removed = false;
    const series = () => ({ setData: vi.fn(), createPriceLine: vi.fn(() => ({})), removePriceLine: vi.fn() });
    return {
      addSeries: series, addPane: () => ({ setHeight: vi.fn() }), applyOptions: vi.fn(),
      timeScale: () => ({ fitContent: vi.fn(), scrollToRealTime: vi.fn() }),
      removeSeries: vi.fn(() => { if (chartMock.removed) throw new Error("Value is undefined"); }),
      remove: vi.fn(() => { chartMock.removed = true; }),
    };
  },
}));

import { demoSnapshot } from "../demo";
import { SignalCanvas } from "./SignalCanvas";


describe("SignalCanvas", () => {
  it("does not remove indicator series from an already destroyed chart", () => {
    chartMock.removed = false;
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    const candles = Array.from({ length: 24 }, (_, index) => ({ timestamp: 1_787_830_000 + index * 300, open: "100", high: "102", low: "99", close: "101", volume: "12" }));
    const view = render(<StrictMode><SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={candles} health={undefined} /></StrictMode>);
    expect(() => view.unmount()).not.toThrow();
  });

  it("never substitutes fabricated candles when live data is unavailable", () => {
    render(<SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={[]} health={undefined} />);
    expect(screen.getByText("暂无可验证的实时 K 线")).toBeVisible();
    expect(screen.queryByText("5m · COMPOSITE")).not.toBeInTheDocument();
  });

  it("shows the selected symbol market status", () => {
    render(<SignalCanvas
      selected={demoSnapshot.opportunities[0]}
      mode="live"
      candles={[]}
      health={{ symbol: "BTCUSDT", status: "unavailable", observed_at: null, latency_ms: 0, reason: "timeout" }}
    />);
    expect(screen.getByText("BTC 行情不可用")).toBeVisible();
  });

  it("labels a forming market card as observation rather than an executable signal", () => {
    render(<SignalCanvas
      selected={{ ...demoSnapshot.opportunities[0], state: "FORMING", order_plan: null, title: "实时市场观察 · 等待触发" }}
      mode="live"
      candles={[]}
      health={{ symbol: "BTCUSDT", status: "healthy", observed_at: new Date().toISOString(), latency_ms: 20, reason: null }}
    />);
    expect(screen.getByText("观察强度")).toBeVisible();
    expect(screen.getByText("实时市场观察 · 等待触发")).toBeVisible();
  });

  it("surfaces unavailable news as an explicit bias instead of fabricating it", () => {
    render(<SignalCanvas selected={{ ...demoSnapshot.opportunities[0], analysis: {
      opportunity_score: 70, confidence: 72, p_tp_before_sl: "0.62", expected_value: "0.11", evidence_conflict: "0.14", is_tradeable: true,
      market_regime: "TREND", signal_type: "trend_continuation", smart_money_bias: "BULLISH", derivatives_bias: "BULLISH", order_flow_bias: "BULLISH", news_bias: "UNAVAILABLE",
    } }} mode="live" candles={[]} health={undefined} />);
    expect(screen.getByText("NEWS UNAVAILABLE")).toBeVisible();
  });

  it("offers timeframe plus primary and secondary indicator controls", () => {
    render(<SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={[]} health={undefined} />);
    expect(screen.getAllByRole("button", { name: "5m" }).at(-1)).toBeVisible();
    expect(screen.getAllByLabelText("主图指标").at(-1)).toBeVisible();
    expect(screen.getAllByLabelText("副图指标").at(-1)).toBeVisible();
  });

  it("marks the clicked chart timeframe as selected", () => {
    render(<SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={[]} health={undefined} />);
    const hour = screen.getAllByRole("button", { name: "1h" }).at(-1)!;
    fireEvent.click(hour);
    expect(hour).toHaveAttribute("aria-pressed", "true");
  });

  it("applies primary and secondary indicator selections instead of leaving decorative controls", () => {
    render(<SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={[]} health={undefined} />);
    const primary = screen.getAllByLabelText("主图指标").at(-1)!;
    const secondary = screen.getAllByLabelText("副图指标").at(-1)!;
    fireEvent.change(primary, { target: { value: "BOLL" } });
    fireEvent.change(secondary, { target: { value: "MACD" } });
    expect(primary).toHaveValue("BOLL");
    expect(secondary).toHaveValue("MACD");
  });
});

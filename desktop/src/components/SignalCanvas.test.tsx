import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

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

afterEach(() => vi.unstubAllGlobals());

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

  it("keeps the visible chart mounted when the five-second market snapshot replaces equivalent candles", async () => {
    const candles = Array.from({ length: 24 }, (_, index) => ({ timestamp: 1_787_830_000 + index * 300, open: "100", high: "102", low: "99", close: "101", volume: "12" }));
    let keepSecondRequestPending!: () => void;
    const secondRequest = new Promise<Response>((resolve) => { keepSecondRequestPending = () => resolve({ ok: true, json: async () => candles } as Response); });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, json: async () => candles }).mockImplementationOnce(() => secondRequest));
    const view = render(<SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={candles} health={undefined} />);
    await waitFor(() => expect(screen.getByLabelText("北京时间 5m K 线图")).toBeVisible());
    view.rerender(<SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={[...candles]} health={undefined} />);
    expect(screen.getByLabelText("北京时间 5m K 线图")).toBeVisible();
    keepSecondRequestPending();
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

  it("gives an on-chain wallet card an explicit flow detail and market benchmark", () => {
    render(<SignalCanvas
      selected={{ ...demoSnapshot.opportunities[0], source: "SMART_MONEY", symbol: "ONCHAIN", market_symbol: "BTCUSDT", title: "公开钱包追踪", source_label: "BSC · Binance Web3 公开钱包", evidence: [{ code: "wallet", text: "钱包 0xabc 出现新的链上活动", weight: 18, value: null, source: "binance" }] }}
      mode="live"
      candles={[]}
      health={undefined}
    />);
    expect(screen.getByText("钱包流向详情")).toBeVisible();
    expect(screen.getByText("市场基准 · BTC/USDT")).toBeVisible();
    expect(screen.getByText("BSC · Binance Web3 公开钱包")).toBeVisible();
  });

  it("loads the selected wallet token from the on-chain OHLCV endpoint", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));
    render(<SignalCanvas
      selected={{ ...demoSnapshot.opportunities[0], source: "SMART_MONEY", symbol: "MEMESTOCK", onchain_token_address: "0xtoken", title: "公开钱包追踪", source_label: "BSC · Binance Web3 公开钱包" }}
      mode="live"
      candles={[]}
      health={undefined}
    />);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/api/v1/onchain/bsc/0xtoken/candles?interval=5"), expect.anything()));
    expect(screen.getByText("链上池 · MEMESTOCK / BSC")).toBeVisible();
  });

  it("surfaces unavailable news as an explicit bias instead of fabricating it", () => {
    render(<SignalCanvas selected={{ ...demoSnapshot.opportunities[0], analysis: {
      opportunity_score: 70, confidence: 72, p_tp_before_sl: "0.62", expected_value: "0.11", evidence_conflict: "0.14", is_tradeable: true,
      market_regime: "TREND", signal_type: "trend_continuation", smart_money_bias: "BULLISH", derivatives_bias: "BULLISH", order_flow_bias: "BULLISH", news_bias: "UNAVAILABLE",
    } }} mode="live" candles={[]} health={undefined} />);
    expect(screen.getByText("NEWS UNAVAILABLE")).toBeVisible();
  });

  it("shows the auditable trade decision gates instead of a black-box score", () => {
    render(<SignalCanvas selected={{ ...demoSnapshot.opportunities[0], analysis: {
      opportunity_score: 70, confidence: 72, p_tp_before_sl: "0.62", expected_value: "0.11", evidence_conflict: "0.14", is_tradeable: true,
      market_regime: "TREND", signal_type: "trend_continuation", smart_money_bias: "BULLISH", derivatives_bias: "BULLISH", order_flow_bias: "BULLISH", news_bias: "UNAVAILABLE",
      decision: { outcome: "TRADE", gates: [
        { key: "tp_before_sl", label: "TP 先于 SL 概率", passed: true, observed: "0.62", required: "0.56" },
        { key: "expected_value", label: "净期望值", passed: true, observed: "0.11", required: "0" },
      ] },
      calibration: { settled: 1, mean_predicted: "0.68", observed_win_rate: "1", absolute_error: "0.32", status: "INSUFFICIENT" },
    } }} mode="live" candles={[]} health={undefined} />);
    expect(screen.getByText("可交易 · 2/2 门槛通过")).toBeVisible();
    expect(screen.getByLabelText("TP 先于 SL 概率")).toBeVisible();
    expect(screen.getByText("策略校准：样本不足（1 笔已结算，不宣称胜率）")).toBeVisible();
  });

  it("offers timeframe plus primary and secondary indicator controls", () => {
    render(<SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={[]} health={undefined} />);
    expect(screen.getAllByRole("button", { name: "5m" }).at(-1)).toBeVisible();
    expect(screen.getAllByLabelText("主图指标").at(-1)).toBeVisible();
    expect(screen.getAllByLabelText("副图指标").at(-1)).toBeVisible();
  });

  it("offers derivatives-focused CVD, open-interest, and funding indicators", () => {
    render(<SignalCanvas selected={demoSnapshot.opportunities[0]} mode="live" candles={[]} health={undefined} />);
    const secondary = screen.getAllByLabelText("副图指标").at(-1)!;
    expect(secondary).toHaveTextContent("CVD（成交方向代理）");
    expect(secondary).toHaveTextContent("OI");
    expect(secondary).toHaveTextContent("资金费率");
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

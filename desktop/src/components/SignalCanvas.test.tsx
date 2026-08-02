import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { demoSnapshot } from "../demo";
import { SignalCanvas } from "./SignalCanvas";


describe("SignalCanvas", () => {
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
});

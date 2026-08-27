import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CyclePanel } from "./CyclePanel";

describe("CyclePanel", () => {
  afterEach(cleanup);
  it("opens on demand and explains the returned phase", () => {
    render(<CyclePanel cycle={{ height: 840000, index: "0.5", phase: "BULL_MID", market_bias: "BULLISH", blocks_to_halving: 0 }} />);
    fireEvent.click(screen.getByRole("button", { name: "BTC 周期" }));
    expect(screen.getByText("模型牛市中期")).toBeVisible();
    expect(screen.getByText("840,000")).toBeVisible();
  });

  it("does not show a fabricated conclusion without height data", () => {
    render(<CyclePanel cycle={null} />);
    fireEvent.click(screen.getByRole("button", { name: "BTC 周期" }));
    expect(screen.getByText("区块高度数据暂不可用")).toBeVisible();
  });
});

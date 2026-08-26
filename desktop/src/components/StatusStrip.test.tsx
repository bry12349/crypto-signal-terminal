import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusStrip } from "./StatusStrip";
import { demoSnapshot } from "../demo";
import type { Health } from "../types";


describe("StatusStrip", () => {
  it("shows actual healthy-symbol coverage", () => {
    const health: Health = {
      mode: "live",
      market: "degraded",
      dune: "not_configured",
      market_detail: {
        overall: "degraded",
        healthy_count: 11,
        expected_count: 12,
        symbols: {},
      },
    };
    render(<StatusStrip health={health} connected items={demoSnapshot.opportunities} />);
    expect(screen.getByText("11/12 币种健康")).toBeVisible();
  });
});

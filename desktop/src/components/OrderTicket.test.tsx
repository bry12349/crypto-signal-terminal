import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrderTicket } from "./OrderTicket";
import { demoSnapshot } from "../demo";


describe("OrderTicket", () => {
  afterEach(() => vi.unstubAllGlobals());
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
});

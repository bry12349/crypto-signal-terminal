import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OrderTicket } from "./OrderTicket";


describe("OrderTicket", () => {
  it("never renders an execution button without a complete plan", () => {
    render(<OrderTicket opportunity={null} />);
    expect(screen.getByText("等待可执行结构")).toBeVisible();
    expect(screen.queryByRole("button", { name: "准备模拟订单" })).not.toBeInTheDocument();
  });
});

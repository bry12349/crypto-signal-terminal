import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TelegramOnboarding } from "./TelegramOnboarding";


describe("TelegramOnboarding", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends credentials to the local service and clears secret inputs", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ telegram: true, bot: false, dune: false }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: "waiting_scan", qr_image: "data:image/svg+xml;base64,dGVzdA==", error: null }), { status: 200, headers: { "content-type": "application/json" } }));
    render(<TelegramOnboarding />);
    fireEvent.click(screen.getByRole("button", { name: "配置 Telegram" }));
    fireEvent.change(screen.getByLabelText("API ID"), { target: { value: "123" } });
    fireEvent.change(screen.getByLabelText("API Hash"), { target: { value: "private-hash" } });
    fireEvent.click(screen.getByRole("button", { name: "安全保存" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8765/api/v1/settings/credentials");
    expect(screen.getByLabelText("API Hash")).toHaveValue("");
    expect(screen.getByText("请使用 Telegram 手机端扫码授权")).toBeVisible();
    expect(screen.getByRole("img", { name: "Telegram 登录二维码" })).toBeVisible();
  });
});

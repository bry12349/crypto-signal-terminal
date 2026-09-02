import { describe, expect, it } from "vitest";

import { mergeSignalPaths } from "./store";

describe("mergeSignalPaths", () => {
  it("labels a public on-chain wallet roster as tracking rather than an entry candidate", () => {
    const opportunities = mergeSignalPaths({
      mode: "live",
      opportunities: [],
      candles: {},
      smart_money: [{
        id: "onchain-wallet:0xabc:1",
        symbol: "ONCHAIN",
        kind: "ONCHAIN_CLUSTER",
        direction: "LONG",
        score: 84,
        observed_at: "2026-08-28T00:00:00Z",
        wallet: "0xabc",
        chain: "BSC · Binance Web3 公开钱包",
        token_address: "0xtoken",
        evidence: [],
      }],
    });

    expect(opportunities[0].title).toBe("公开钱包追踪")
    expect(opportunities[0].risk).toContain("不等同于 CEX 开仓")
    expect(opportunities[0].market_symbol).toBe("BTCUSDT")
    expect(opportunities[0].onchain_token_address).toBe("0xtoken")
  });

  it("uses BTC as the chart benchmark when a wallet token has no verified perpetual market", () => {
    const opportunities = mergeSignalPaths({
      mode: "live",
      opportunities: [],
      candles: { BTCUSDT: [], ETHUSDT: [] },
      smart_money: [{
        id: "onchain-wallet:0xmemestock:1", symbol: "MEMESTOCK", kind: "ONCHAIN_CLUSTER", direction: "LONG", score: 88,
        observed_at: "2026-08-29T00:00:00Z", wallet: "0xmemestock", chain: "BSC · Binance Web3 公开钱包", evidence: [],
      }],
    });

    expect(opportunities[0].market_symbol).toBe("BTCUSDT");
  });

  it("keeps a human token name while preserving its on-chain chart identity", () => {
    const opportunities = mergeSignalPaths({
      mode: "live", opportunities: [], candles: {}, smart_money: [{
        id: "onchain-wallet:0xabc:2", symbol: "CHAINBEEA1D", display_symbol: "牛来", kind: "ONCHAIN_CLUSTER", direction: "LONG", score: 88,
        observed_at: "2026-08-29T00:00:00Z", wallet: "0xabc", chain: "BSC · Binance Web3 公开钱包", token_address: "0xbeea1d", evidence: [],
      }],
    });
    expect(opportunities[0].symbol).toBe("牛来");
    expect(opportunities[0].onchain_token_address).toBe("0xbeea1d");
  });
});

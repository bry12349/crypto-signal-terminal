import type { Snapshot } from "./types";

const now = new Date().toISOString();
const expires = new Date(Date.now() + 4 * 60_000).toISOString();

export const demoSnapshot: Snapshot = {
  mode: "demo",
  opportunities: [
    {
      id: "trend:BTCUSDT:demo",
      symbol: "BTCUSDT",
      source: "NATIVE",
      state: "ENTRY_VALID",
      confidence: 83,
      title: "日内趋势跟随",
      risk: "失守 66,810 后趋势失效",
      source_label: null,
      updated_at: now,
      evidence: [
        { code: "trend", text: "4h 与 1h 多头结构一致", weight: 28 },
        { code: "pullback", text: "15m 回踩 VWAP 后重新收复", weight: 22 },
        { code: "flow", text: "主动买入与 OI 同步增加", weight: 18, value: "0.58" },
      ],
      order_plan: {
        direction: "LONG", order_type: "LIMIT", entry_low: "67180", entry_high: "67240", stop: "66810",
        targets: ["67840", "68420"], target_allocations: ["0.5", "0.5"], expires_at: expires,
        max_slippage_bps: "8", suggested_quantity: "0.067", risk_amount: "25", reward_to_risk: "2.31",
        invalidation: "5m 收盘跌破 66810", estimated_fees: "2.71",
      },
    },
    {
      id: "alt:SOLUSDT:demo",
      symbol: "SOLUSDT",
      source: "NATIVE",
      state: "ENTRY_VALID",
      confidence: 86,
      title: "临界瀑布",
      risk: "BTC 临近日内支撑，防止快速反抽",
      source_label: null,
      updated_at: now,
      evidence: [
        { code: "compression", text: "30m 压缩区下沿被有效击穿", weight: 24, value: "11" },
        { code: "oi", text: "OI 8 分钟增加 8.1%", weight: 24, value: "0.081" },
        { code: "flow", text: "主动卖出占比 67%，三所同步", weight: 22, value: "-0.66" },
      ],
      order_plan: {
        direction: "SHORT", order_type: "LIMIT", entry_low: "146.20", entry_high: "146.48", stop: "147.42",
        targets: ["144.62", "142.90"], target_allocations: ["0.5", "0.5"], expires_at: expires,
        max_slippage_bps: "8", suggested_quantity: "25.6", risk_amount: "25", reward_to_risk: "2.58",
        invalidation: "5m 重新站上 147.42", estimated_fees: "2.25",
      },
    },
    {
      id: "alt:SUIUSDT:forming",
      symbol: "SUIUSDT",
      source: "NATIVE",
      state: "ARMED",
      confidence: 72,
      title: "临界起爆 · 待触发",
      risk: "等待 1.086 放量突破",
      source_label: null,
      updated_at: now,
      evidence: [
        { code: "compression", text: "波动率处于 30 日 9% 分位", weight: 24 },
        { code: "oi", text: "价格横盘但 OI 持续抬升", weight: 22 },
      ],
      order_plan: null,
    },
  ],
  smart_money: [
    {
      id: "smart-flow:SOLUSDT:demo",
      symbol: "SOLUSDT",
      kind: "DERIVATIVES_FLOW",
      direction: "SHORT",
      score: 88,
      observed_at: now,
      evidence: [
        { code: "persistent", text: "大额主动卖单连续覆盖 4 个窗口", weight: 30 },
        { code: "oi", text: "新空仓同步进入而非多头平仓", weight: 25 },
      ],
    },
  ],
  confirmations: [
    {
      id: "telegram:demo",
      verdict: "CONFIRMED",
      confidence: 84,
      analyzed_at: now,
      evidence: [
        { code: "trend", text: "频道方向与 1h 空头结构一致", weight: 18 },
        { code: "flow", text: "主动卖出与 OI 同步确认", weight: 16 },
      ],
      reason_codes: [],
      signal: { symbol: "SOLUSDT", direction: "SHORT", channel_id: 1001 },
      order_plan: null,
    },
  ],
};

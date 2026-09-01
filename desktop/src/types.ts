export type Direction = "LONG" | "SHORT";
export type LifecycleState =
  | "FORMING"
  | "ARMED"
  | "TRIGGERED"
  | "ENTRY_VALID"
  | "MANAGING"
  | "CLOSED"
  | "INVALIDATED"
  | "EXPIRED";

export interface Evidence {
  code: string;
  text: string;
  weight: number;
  value?: string | null;
  source?: string | null;
}

export interface OrderPlan {
  direction: Direction;
  order_type: "MARKET" | "LIMIT" | "STOP_MARKET";
  entry_low: string;
  entry_high: string;
  stop: string;
  targets: string[];
  target_allocations: string[];
  expires_at: string;
  max_slippage_bps: string;
  suggested_quantity: string;
  risk_amount: string;
  reward_to_risk: string;
  invalidation: string;
  estimated_fees: string;
}

export interface SignalAnalysis {
  opportunity_score: number;
  confidence: number;
  p_tp_before_sl: string;
  expected_value: string;
  evidence_conflict: string;
  is_tradeable: boolean;
  market_regime: string;
  signal_type: string;
  smart_money_bias: string;
  derivatives_bias: string;
  order_flow_bias: string;
  news_bias: string;
  calibration?: {
    settled: number;
    mean_predicted: string;
    observed_win_rate: string;
    absolute_error: string;
    brier_score?: string;
    status: "INSUFFICIENT" | "VALIDATED" | "DEGRADED";
  };
  decision?: {
    outcome: "TRADE" | "NO_TRADE";
    gates: { key: string; label: string; passed: boolean; observed: string; required: string }[];
  };
}

export interface Opportunity {
  id: string;
  symbol: string;
  source: "NATIVE" | "SMART_MONEY" | "DEMO";
  state: LifecycleState;
  confidence: number;
  title: string | null;
  risk: string | null;
  source_label: string | null;
  market_symbol?: string | null;
  onchain_token_address?: string | null;
  updated_at: string;
  evidence: Evidence[];
  order_plan: OrderPlan | null;
  analysis?: SignalAnalysis | null;
}

export interface SmartMoneyCandidate {
  id: string;
  symbol: string;
  kind: "ACCUMULATION" | "DISTRIBUTION" | "DERIVATIVES_FLOW" | "ONCHAIN_CLUSTER";
  direction: Direction;
  score: number;
  observed_at: string;
  evidence: Evidence[];
  wallet?: string | null;
  chain?: string | null;
  token_address?: string | null;
}

export interface Candle {
  timestamp: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface Snapshot {
  mode: string;
  opportunities: Opportunity[];
  smart_money: SmartMoneyCandidate[];
  candles?: Record<string, Candle[]>;
}

export interface Health {
  mode: string;
  market: string;
  dune: string;
  market_detail: MarketHealthDetail;
}

export interface BtcCycle {
  height: number;
  index: string;
  phase: string;
  market_bias: string;
  blocks_to_halving: number;
}

export interface MarketSymbolHealth {
  symbol: string;
  status: "healthy" | "degraded" | "unavailable" | "unknown";
  observed_at: string | null;
  latency_ms: number;
  reason: string | null;
}

export interface MarketHealthDetail {
  overall: string;
  healthy_count: number;
  expected_count: number;
  symbols: Record<string, MarketSymbolHealth>;
}

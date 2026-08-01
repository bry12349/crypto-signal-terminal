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

export interface Opportunity {
  id: string;
  symbol: string;
  source: "NATIVE" | "TELEGRAM" | "SMART_MONEY" | "DEMO";
  state: LifecycleState;
  confidence: number;
  title: string | null;
  risk: string | null;
  source_label: string | null;
  updated_at: string;
  evidence: Evidence[];
  order_plan: OrderPlan | null;
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
}

export interface Confirmation {
  id: string;
  verdict: "CONFIRMED" | "CONDITIONAL" | "REJECTED" | "EXPIRED" | "UNPARSEABLE";
  confidence: number;
  analyzed_at: string;
  evidence: Evidence[];
  reason_codes: string[];
  order_plan: OrderPlan | null;
  signal: {
    symbol: string | null;
    direction: Direction | null;
    channel_id: number;
  };
}

export interface Snapshot {
  mode: string;
  opportunities: Opportunity[];
  smart_money: SmartMoneyCandidate[];
  confirmations: Confirmation[];
}

export interface Health {
  mode: string;
  market: string;
  telegram: string;
  bot: string;
  dune: string;
}

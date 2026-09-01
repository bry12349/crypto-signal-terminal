import { useMemo, useState } from "react";
import { BrainCircuit, RadioTower, Zap } from "lucide-react";

import type { Opportunity } from "../types";

const priority: Record<Opportunity["state"], number> = {
  ENTRY_VALID: 0, TRIGGERED: 1, MANAGING: 2, ARMED: 3, FORMING: 4,
  INVALIDATED: 5, EXPIRED: 6, CLOSED: 7,
};

const labels: Record<Opportunity["state"], string> = {
  ENTRY_VALID: "可入场", TRIGGERED: "已触发", MANAGING: "持仓中", ARMED: "待触发", FORMING: "形成中",
  INVALIDATED: "已失效", EXPIRED: "已过期", CLOSED: "已结束",
};

const filters = ["全部", "主流", "山寨", "聪明钱"] as const;
type Filter = typeof filters[number];

function SourceIcon({ source }: { source: Opportunity["source"] }) {
  if (source === "SMART_MONEY") return <BrainCircuit size={13} />;
  if (source === "NATIVE") return <Zap size={13} />;
  return <RadioTower size={13} />;
}

function matchesFilter(item: Opportunity, filter: Filter) {
  if (filter === "全部") return true;
  if (filter === "聪明钱") return item.source === "SMART_MONEY";
  if (filter === "主流") return item.symbol === "BTCUSDT" || item.symbol === "ETHUSDT";
  return item.source !== "SMART_MONEY" && item.symbol !== "BTCUSDT" && item.symbol !== "ETHUSDT";
}

function compareSignalQuality(a: Opportunity, b: Opportunity) {
  const actionable = (item: Opportunity) => Number(item.state === "ENTRY_VALID" && item.order_plan !== null && item.analysis?.is_tradeable === true);
  return actionable(b) - actionable(a)
    || Number(b.analysis?.is_tradeable === true) - Number(a.analysis?.is_tradeable === true)
    || priority[a.state] - priority[b.state]
    || Number(b.analysis?.expected_value ?? -1) - Number(a.analysis?.expected_value ?? -1)
    || Number(b.analysis?.p_tp_before_sl ?? 0) - Number(a.analysis?.p_tp_before_sl ?? 0)
    || Number(b.analysis?.opportunity_score ?? 0) - Number(a.analysis?.opportunity_score ?? 0)
    || b.confidence - a.confidence;
}

export function OpportunityStream({ items, selectedId, onSelect }: { items: Opportunity[]; selectedId: string | null; onSelect: (id: string) => void }) {
  const [filter, setFilter] = useState<Filter>("全部");
  const sorted = useMemo(() => items.filter((item) => matchesFilter(item, filter)).sort(compareSignalQuality), [items, filter]);
  const best = useMemo(() => [...items].sort(compareSignalQuality).find((item) => item.state === "ENTRY_VALID" && item.analysis?.is_tradeable), [items]);
  return <aside className="opportunity-rail">
    <div className="rail-heading"><div><span className="eyebrow">LIVE RADAR</span><h2>机会流</h2></div><div className="rail-actions">{best && <button type="button" aria-label="查看最佳信号" onClick={() => { setFilter("全部"); onSelect(best.id); }}>最佳信号</button>}<span className="count-badge">{sorted.length}</span></div></div>
    <div className="filter-row">{filters.map((value) => <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{value}</button>)}</div>
    <div className="opportunity-list">
      {sorted.length === 0 && <div className="empty-state"><RadioTower size={22} /><strong>当前无可执行机会</strong><span>系统正在等待高质量结构</span></div>}
      {sorted.map((item) => {
        const direction = item.order_plan?.direction;
        return <button type="button" key={item.id} data-testid="opportunity" className={`opportunity-card ${selectedId === item.id ? "selected" : ""} ${direction?.toLowerCase() ?? "neutral"}`} onClick={() => onSelect(item.id)}>
          <div className="card-topline"><span className="source-tag"><SourceIcon source={item.source} />{item.source === "SMART_MONEY" ? "聪明钱" : "原生"}</span><span className="state-label"><i className={`state-dot ${item.state.toLowerCase()}`} />{labels[item.state]}</span></div>
          <div className="symbol-line"><strong>{item.symbol.replace("USDT", "")}</strong><span className="contract-label">USDT PERP</span><em>{item.confidence}</em></div>
          <div className="card-title">{item.title ?? "市场结构机会"}</div>
          <div className="micro-evidence">{item.evidence[0]?.text ?? "等待更多确认"}</div>
          <div className="confidence-track"><i style={{ width: `${item.confidence}%` }} /></div>
        </button>;
      })}
    </div>
  </aside>;
}

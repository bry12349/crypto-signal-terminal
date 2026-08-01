import { ArrowDownRight, ArrowUpRight, LockKeyhole, Shield, TimerReset } from "lucide-react";
import type { Opportunity } from "../types";

function price(value: string) {
  const parsed = Number(value);
  return parsed >= 1000 ? parsed.toLocaleString("en-US", { maximumFractionDigits: 2 }) : parsed.toFixed(parsed < 10 ? 4 : 2);
}

export function OrderTicket({ opportunity }: { opportunity: Opportunity | null }) {
  const plan = opportunity?.order_plan;
  if (!opportunity || !plan) {
    return <aside className="order-panel empty-order"><LockKeyhole size={22} /><strong>等待可执行结构</strong><span>触发确认后才会生成订单参数</span></aside>;
  }
  const isLong = plan.direction === "LONG";
  return (
    <aside className={`order-panel ${isLong ? "long" : "short"}`}>
      <div className="ticket-head"><div><span className="eyebrow">EXECUTION PLAN</span><h2>{isLong ? <ArrowUpRight /> : <ArrowDownRight />}{plan.direction}</h2></div><span className="ttl"><TimerReset size={13} />04:36</span></div>
      <div className="entry-block"><span>{plan.order_type} ENTRY</span><strong>{price(plan.entry_low)}<i>—</i>{price(plan.entry_high)}</strong><small>最大滑点 {plan.max_slippage_bps} bps</small></div>
      <div className="levels">
        <div className="stop"><span>STOP LOSS</span><strong>{price(plan.stop)}</strong><small>-1R · 风险 ${Number(plan.risk_amount).toFixed(2)}</small></div>
        {plan.targets.map((target, index) => <div className="target" key={target}><span>TAKE PROFIT {index + 1}</span><strong>{price(target)}</strong><small>{Number(plan.target_allocations[index]) * 100}% 仓位</small></div>)}
      </div>
      <div className="rr-row"><div><span>NET R:R</span><strong>1 : {Number(plan.reward_to_risk).toFixed(2)}</strong></div><div><span>SIZE</span><strong>{Number(plan.suggested_quantity).toFixed(3)}</strong></div></div>
      <div className="invalidation"><Shield size={15} /><div><span>失效条件</span><strong>{plan.invalidation}</strong></div></div>
      <button className="prepare-order">准备模拟订单 <span>↵</span></button>
      <p className="execution-note">v0.1.0 仅生成模拟订单，不会触发真实交易</p>
    </aside>
  );
}

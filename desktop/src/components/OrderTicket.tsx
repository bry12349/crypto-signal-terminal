import { useCallback, useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, LockKeyhole, Shield, TimerReset } from "lucide-react";
import type { Opportunity } from "../types";

const API = "http://127.0.0.1:8765";

function price(value: string) {
  const parsed = Number(value);
  return parsed >= 1000 ? parsed.toLocaleString("en-US", { maximumFractionDigits: 2 }) : parsed.toFixed(parsed < 10 ? 4 : 2);
}

export function OrderTicket({ opportunity }: { opportunity: Opportunity | null }) {
  const [status, setStatus] = useState<"idle" | "sending" | "prepared" | "error">("idle");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const plan = opportunity?.order_plan;
  const prepare = useCallback(async () => {
    if (!opportunity || !plan || status === "sending") return;
    setStatus("sending");
    setErrorDetail(null);
    try {
      const response = await fetch(`${API}/api/v1/paper-orders`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ opportunity_id: opportunity.id }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: "" })) as { detail?: string };
        const detail = payload.detail === "Symbol market data is stale or unavailable"
          ? "该币种行情已过期或不可用，请等待下一轮刷新"
          : payload.detail === "Opportunity was produced from unhealthy market data"
            ? "该机会生成时的数据不健康，已禁止准备订单"
            : payload.detail === "Opportunity expired; refresh market analysis"
              ? "机会有效期已结束，请等待重新分析"
              : "模拟订单被本地风控拒绝";
        throw new Error(detail);
      }
      setStatus("prepared");
    } catch (error) {
      setStatus("error");
      setErrorDetail(error instanceof Error ? error.message : "模拟订单被本地风控拒绝");
    }
  }, [opportunity, plan, status]);

  useEffect(() => { setStatus("idle"); setErrorDetail(null); }, [opportunity?.id]);
  useEffect(() => {
    const handler = () => { void prepare(); };
    window.addEventListener("prepare-order", handler);
    return () => window.removeEventListener("prepare-order", handler);
  }, [prepare]);

  if (!opportunity || !plan) {
    return <aside className="order-panel empty-order"><LockKeyhole size={22} /><strong>等待可执行结构</strong><span>触发确认后才会生成订单参数</span></aside>;
  }
  const isLong = plan.direction === "LONG";
  const ttlSeconds = Math.max(0, Math.floor((new Date(plan.expires_at).getTime() - Date.now()) / 1000));
  const ttl = `${String(Math.floor(ttlSeconds / 60)).padStart(2, "0")}:${String(ttlSeconds % 60).padStart(2, "0")}`;
  const buttonText = status === "sending" ? "正在复核…" : status === "prepared" ? "模拟订单已准备" : status === "error" ? "已失效，请刷新" : "准备模拟订单";
  return (
    <aside className={`order-panel ${isLong ? "long" : "short"}`}>
      <div className="ticket-head"><div><span className="eyebrow">EXECUTION PLAN</span><h2>{isLong ? <ArrowUpRight /> : <ArrowDownRight />}{plan.direction}</h2></div><span className="ttl"><TimerReset size={13} />{ttl}</span></div>
      <div className="entry-block"><span>{plan.order_type} ENTRY</span><strong>{price(plan.entry_low)}<i>—</i>{price(plan.entry_high)}</strong><small>最大滑点 {plan.max_slippage_bps} bps</small></div>
      <div className="levels">
        <div className="stop"><span>STOP LOSS</span><strong>{price(plan.stop)}</strong><small>-1R · 风险 ${Number(plan.risk_amount).toFixed(2)}</small></div>
        {plan.targets.map((target, index) => <div className="target" key={target}><span>TAKE PROFIT {index + 1}</span><strong>{price(target)}</strong><small>{Number(plan.target_allocations[index]) * 100}% 仓位</small></div>)}
      </div>
      <div className="rr-row"><div><span>NET R:R</span><strong>1 : {Number(plan.reward_to_risk).toFixed(2)}</strong></div><div><span>SIZE</span><strong>{Number(plan.suggested_quantity).toFixed(3)}</strong></div></div>
      <div className="invalidation"><Shield size={15} /><div><span>失效条件</span><strong>{plan.invalidation}</strong></div></div>
      <button className="prepare-order" onClick={() => void prepare()} disabled={status === "sending" || status === "prepared"}>{buttonText} <span>↵</span></button>
      {errorDetail && <div className="order-error" role="alert">{errorDetail}</div>}
      <p className="execution-note">默认按 $10,000 权益、单笔 0.25% 风险；v0.2.0 仅生成模拟订单</p>
    </aside>
  );
}

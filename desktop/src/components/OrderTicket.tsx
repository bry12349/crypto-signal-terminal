import { useCallback, useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Ban, CheckCircle2, LockKeyhole, Shield, Target, TimerReset } from "lucide-react";
import type { Opportunity } from "../types";

const API = "http://127.0.0.1:8765";

function price(value: string) {
  const parsed = Number(value);
  return parsed >= 1000 ? parsed.toLocaleString("en-US", { maximumFractionDigits: 2 }) : parsed.toFixed(parsed < 10 ? 4 : 2);
}

function orderTypeLabel(type: "MARKET" | "LIMIT" | "STOP_MARKET") {
  if (type === "MARKET") return "市价执行";
  if (type === "LIMIT") return "限价挂单";
  return "突破触发";
}

export function OrderTicket({ opportunity }: { opportunity: Opportunity | null }) {
  const [status, setStatus] = useState<"idle" | "sending" | "prepared" | "error">("idle");
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const plan = opportunity?.order_plan;
  const planExpiry = plan ? Date.parse(plan.expires_at) : Number.NaN;
  const expired = Boolean(plan && (!Number.isFinite(planExpiry) || planExpiry <= Date.now()));
  const actionable = Boolean(plan && !expired && opportunity?.state === "ENTRY_VALID" && opportunity.analysis?.is_tradeable !== false);
  const prepare = useCallback(async () => {
    if (!opportunity || !plan || !actionable || status === "sending") return;
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
  }, [actionable, opportunity, plan, status]);

  useEffect(() => { setStatus("idle"); setErrorDetail(null); }, [opportunity?.id]);
  useEffect(() => {
    const handler = () => { void prepare(); };
    window.addEventListener("prepare-order", handler);
    return () => window.removeEventListener("prepare-order", handler);
  }, [prepare]);

  if (!opportunity) {
    return <aside className="order-panel empty-order"><LockKeyhole size={22} /><strong>等待可执行结构</strong><span>选择机会后查看交易决策</span></aside>;
  }

  if (!actionable || !plan) {
    const blockedGates = opportunity.analysis?.decision?.gates.filter((gate) => !gate.passed) ?? [];
    const blockedReasons = expired ? ["执行窗口已经结束"] : blockedGates.length ? blockedGates.slice(0, 3).map((gate) => gate.label) : opportunity.evidence.slice(0, 3).map((item) => item.text);
    return (
      <aside className="order-panel decision-sidebar no-trade">
        <section className="decision-hero">
          <span className="eyebrow">TRADE DECISION</span>
          <div className="decision-state"><Ban size={24} /><h2>现在不能做</h2></div>
          <p>{expired ? "信号已过期，等待重新分析" : opportunity.risk ?? "当前结构尚未满足触发、数据质量或风控条件"}</p>
          <div className="decision-meta"><strong>继续观察</strong><strong>可靠度 {opportunity.confidence}/100</strong></div>
          <small>可靠度是结构评分，不等于历史胜率</small>
        </section>
        <section className="decision-reasons blocked-reasons">
          <span className="eyebrow">WHY NOT</span>
          <h3>暂不做单理由</h3>
          {blockedReasons.map((text, index) => (
            <div className="reason-row" key={`${index}:${text}`}><span>{index + 1}</span><p>{text}</p></div>
          ))}
        </section>
        <div className="decision-lock"><LockKeyhole size={16} /><span>订单入口已锁定，条件满足后自动开放</span></div>
      </aside>
    );
  }
  const isLong = plan.direction === "LONG";
  const ttlSeconds = Math.max(0, Math.floor((new Date(plan.expires_at).getTime() - Date.now()) / 1000));
  const ttl = `${String(Math.floor(ttlSeconds / 60)).padStart(2, "0")}:${String(ttlSeconds % 60).padStart(2, "0")}`;
  const buttonText = status === "sending" ? "正在复核…" : status === "prepared" ? "模拟订单已准备" : status === "error" ? "已失效，请刷新" : "准备模拟订单";
  return (
    <aside className={`order-panel decision-sidebar ${isLong ? "long" : "short"}`}>
      <section className="decision-hero">
        <div className="decision-overline"><span className="eyebrow">TRADE DECISION</span><span className="ttl"><TimerReset size={13} />剩余 {ttl}</span></div>
        <div className="decision-state">{isLong ? <ArrowUpRight size={26} /> : <ArrowDownRight size={26} />}<h2>{isLong ? "可以做多" : "可以做空"}</h2></div>
        <div className="decision-meta"><strong>{orderTypeLabel(plan.order_type)}</strong><strong>可靠度 {opportunity.confidence}/100</strong></div>
        <small>可靠度是结构评分，不等于历史胜率</small>
      </section>

      <section className="decision-prices" aria-label="交易价格计划">
        <div className="price-level entry-level"><span>入场区间</span><strong>{price(plan.entry_low)}<i>—</i>{price(plan.entry_high)}</strong><small>{orderTypeLabel(plan.order_type)} · 最大滑点 {plan.max_slippage_bps} bps</small></div>
        <div className="price-level stop-level"><span>止损</span><strong>{price(plan.stop)}</strong><small>风险 ${Number(plan.risk_amount).toFixed(2)}</small></div>
        {plan.targets.map((target, index) => <div className="price-level target-level" key={target}><span>止盈 {index + 1}</span><strong>{price(target)}</strong><small>减仓 {Number(plan.target_allocations[index]) * 100}%</small></div>)}
      </section>

      <section className="decision-reasons">
        <span className="eyebrow">WHY THIS TRADE</span>
        <h3>做单理由</h3>
        {opportunity.evidence.slice(0, 3).map((item, index) => <div className="reason-row" key={item.code}><span>{index + 1}</span><p>{item.text}{item.value ? <small>实时值 {item.value}</small> : null}</p><CheckCircle2 size={15} /></div>)}
      </section>

      <div className="rr-row"><div><span>盈亏比</span><strong>1 : {Number(plan.reward_to_risk).toFixed(2)}</strong></div><div><span>建议数量</span><strong>{Number(plan.suggested_quantity).toFixed(3)}</strong></div></div>
      <div className="invalidation"><Shield size={15} /><div><span>失效条件</span><strong>{plan.invalidation}</strong></div></div>
      {opportunity.risk && <div className="decision-risk"><Target size={15} /><div><span>主要风险</span><strong>{opportunity.risk}</strong></div></div>}
      <button className="prepare-order" onClick={() => void prepare()} disabled={status === "sending" || status === "prepared"}>{buttonText} <span>↵</span></button>
      {errorDetail && <div className="order-error" role="alert">{errorDetail}</div>}
      <p className="execution-note">默认按 $10,000 权益、单笔 0.25% 风险；当前仅生成模拟订单</p>
    </aside>
  );
}

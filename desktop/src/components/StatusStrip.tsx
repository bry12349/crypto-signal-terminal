import { Activity, Bot, Radio, ShieldCheck, WalletCards } from "lucide-react";
import type { Health, Opportunity } from "../types";

export function StatusStrip({ health, connected, items }: { health: Health; connected: boolean; items: Opportunity[] }) {
  const btc = items.find((item) => item.symbol === "BTCUSDT" && item.source === "NATIVE");
  const btcRegime = btc?.order_plan?.direction === "LONG" ? "BTC 日内偏多" : btc?.order_plan?.direction === "SHORT" ? "BTC 日内偏空" : "BTC 等待结构";
  const altCount = items.filter((item) => item.source === "NATIVE" && !["BTCUSDT", "ETHUSDT"].includes(item.symbol)).length;
  const connectionLabel = !connected ? "本地服务离线" : health.mode === "live" ? "实时扫描" : "演示数据";
  return (
    <header className="status-strip">
      <div className="brand-mark">CST</div>
      <div className="regime-pill"><Activity size={14} /> {btcRegime}</div>
      <div className="status-metric"><span>ALT RADAR</span><strong>{altCount ? `${altCount} 个临界候选` : "暂无临界机会"}</strong></div>
      <div className="status-metric"><span>DATA MODE</span><strong>{health.mode === "live" ? "PUBLIC LIVE" : "DEMO"}</strong></div>
      <div className="status-metric"><span>EVENT RISK</span><strong className="muted">宏观事件暂未接入</strong></div>
      <div className="status-spacer" />
      <div className={`connection ${connected && health.mode === "live" ? "live" : "demo"}`}><Radio size={13} />{connectionLabel}</div>
      <div className="service-icons" aria-label="service health">
        <ShieldCheck size={14} className={health.market === "healthy" ? "ok" : "off"} />
        <Bot size={14} className={health.telegram === "healthy" ? "ok" : "off"} />
        <WalletCards size={14} className={health.dune === "healthy" ? "ok" : "off"} />
      </div>
    </header>
  );
}

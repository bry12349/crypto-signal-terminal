import { useEffect, useMemo, useState } from "react";
import { Crosshair, History, Radar, Settings2 } from "lucide-react";

import { OpportunityStream } from "./components/OpportunityStream";
import { OrderTicket } from "./components/OrderTicket";
import { SignalCanvas } from "./components/SignalCanvas";
import { StatusStrip } from "./components/StatusStrip";
import { TelegramOnboarding } from "./components/TelegramOnboarding";
import { useTerminalStore } from "./store";

export default function App() {
  const { snapshot, opportunities, health, connected, selectedId, select, load, connectEvents } = useTerminalStore();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const selected = useMemo(() => opportunities.find((item) => item.id === selectedId) ?? null, [opportunities, selectedId]);

  useEffect(() => {
    void load();
    const disconnect = connectEvents();
    const timer = window.setInterval(() => void load(), 15000);
    return () => { window.clearInterval(timer); disconnect(); };
  }, [connectEvents, load]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (!opportunities.length) return;
      const index = Math.max(0, opportunities.findIndex((item) => item.id === selectedId));
      if (event.key.toLowerCase() === "j") select(opportunities[Math.min(opportunities.length - 1, index + 1)].id);
      if (event.key.toLowerCase() === "k") select(opportunities[Math.max(0, index - 1)].id);
      if (event.key === "Enter" && selected?.order_plan) window.dispatchEvent(new Event("prepare-order"));
      if (event.key === "Escape") setSettingsOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [opportunities, select, selected, selectedId]);

  return (
    <div className="terminal">
      <StatusStrip health={health} connected={connected} items={opportunities} />
      <nav className="icon-nav">
        <div className="nav-logo">C</div>
        <button className="active" aria-label="雷达"><Radar /></button>
        <button aria-label="执行"><Crosshair /></button>
        <button aria-label="复盘"><History /></button>
        <div className="nav-spacer" />
        <button aria-label="设置" onClick={() => setSettingsOpen((value) => !value)}><Settings2 /></button>
        <span className="nav-live" />
      </nav>
      <div className="workspace">
        <OpportunityStream items={opportunities} selectedId={selectedId} onSelect={select} />
        <SignalCanvas selected={selected} mode={snapshot.mode} candles={selected ? snapshot.candles?.[selected.symbol] ?? [] : []} />
        <OrderTicket opportunity={selected} />
      </div>
      <footer className="shortcut-bar"><span><kbd>J</kbd><kbd>K</kbd> 切换机会</span><span><kbd>Space</kbd> 展开证据</span><span><kbd>Enter</kbd> 准备订单</span><strong>只在结构完整时发出信号</strong></footer>
      {settingsOpen && <div className="drawer-backdrop" onClick={() => setSettingsOpen(false)}><div onClick={(event) => event.stopPropagation()}><TelegramOnboarding /></div></div>}
    </div>
  );
}

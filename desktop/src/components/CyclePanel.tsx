import { useState } from "react";
import { Activity } from "lucide-react";

export interface BtcCycle {
  height: number;
  index: string;
  phase: string;
  market_bias: string;
  blocks_to_halving: number;
}

const PHASE_LABEL: Record<string, string> = {
  BULL_EARLY: "模型牛市早期", BULL_MID: "模型牛市中期", BULL_LATE: "模型牛市后期",
  BEAR_EARLY: "模型熊市早期", BEAR_MID: "模型熊市中期", BEAR_LATE: "模型熊市末期",
};

export function CyclePanel({ cycle }: { cycle: BtcCycle | null }) {
  const [open, setOpen] = useState(false);
  return <>
    <button className="cycle-trigger" type="button" aria-label="BTC 周期" onClick={() => setOpen((value) => !value)}><Activity size={15} /> BTC 周期</button>
    {open && <aside className="cycle-panel" aria-label="BTC 区块周期分析">
      <header><span>BTC BLOCK CYCLE</span><button type="button" aria-label="关闭周期分析" onClick={() => setOpen(false)}>×</button></header>
      {cycle ? <><strong>{PHASE_LABEL[cycle.phase] ?? cycle.phase}</strong><div className="cycle-index"><span>WWI</span><b>{(Number(cycle.index) * 100).toFixed(1)}%</b></div><dl><div><dt>区块高度</dt><dd>{cycle.height.toLocaleString("en-US")}</dd></div><div><dt>距最近减半</dt><dd>{Math.abs(cycle.blocks_to_halving).toLocaleString("en-US")} blocks</dd></div></dl><p>{cycle.market_bias === "BULLISH" ? "周期环境偏多；仅为顺势结构提供加权，不构成买入建议。" : "周期环境偏空；高 Beta 多头需提高确认门槛。"}</p></> : <div className="cycle-unavailable">区块高度数据暂不可用<br /><small>系统不会用估算值替代真实链上高度。</small></div>}
    </aside>}
  </>;
}

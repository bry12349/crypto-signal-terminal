import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries, ColorType, HistogramSeries, type UTCTimestamp } from "lightweight-charts";
import { AlertTriangle, CheckCircle2, Clock3, Crosshair, Layers3 } from "lucide-react";
import type { Candle, Opportunity } from "../types";

function MiniChart({ selected, candles }: { selected: Opportunity; candles: Candle[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: ref.current.clientHeight,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#687386", fontFamily: "IBM Plex Mono, monospace" },
      grid: { vertLines: { color: "rgba(64,72,88,.12)" }, horzLines: { color: "rgba(64,72,88,.12)" } },
      rightPriceScale: { borderColor: "rgba(85,95,112,.22)" },
      timeScale: { borderColor: "rgba(85,95,112,.22)", timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: "#5d6c84", width: 1 }, horzLine: { color: "#5d6c84", width: 1 } },
    });
    const series = chart.addSeries(CandlestickSeries, { upColor: "#22c78b", downColor: "#f15b6c", wickUpColor: "#22c78b", wickDownColor: "#f15b6c", borderVisible: false });
    series.setData(candles.map((item) => ({
      time: item.timestamp as UTCTimestamp,
      open: Number(item.open), high: Number(item.high), low: Number(item.low), close: Number(item.close),
    })));
    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(candles.map((item) => ({ time: item.timestamp as UTCTimestamp, value: Number(item.volume), color: Number(item.close) >= Number(item.open) ? "rgba(34,199,139,.26)" : "rgba(241,91,108,.26)" })));
    if (selected.order_plan) {
      series.createPriceLine({ price: Number(selected.order_plan.stop), color: "#f15b6c", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "SL" });
      selected.order_plan.targets.forEach((target, index) => series.createPriceLine({ price: Number(target), color: "#22c78b", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: `TP${index + 1}` }));
    }
    chart.timeScale().fitContent();
    const resize = new ResizeObserver(([entry]) => chart.applyOptions({ width: entry.contentRect.width, height: entry.contentRect.height }));
    resize.observe(ref.current);
    return () => { resize.disconnect(); chart.remove(); };
  }, [candles, selected]);
  return <div className="chart" ref={ref} />;
}

export function SignalCanvas({ selected, candles, mode }: { selected: Opportunity | null; candles: Candle[]; mode: string }) {
  if (!selected) return <main className="signal-canvas empty-canvas"><Crosshair size={26} /><h2>当前无可执行机会</h2><p>只有满足触发、流动性与风控条件的结构才会出现在这里。</p></main>;
  const direction = selected.order_plan?.direction;
  return (
    <main className="signal-canvas">
      <div className="instrument-head">
        <div><span className="eyebrow">SELECTED INSTRUMENT</span><h1>{selected.symbol.replace("USDT", "")}<small> / USDT PERP</small></h1></div>
        <div className={`direction-lock ${direction?.toLowerCase() ?? "watch"}`}><span>{direction ?? "WATCH"}</span><strong>{selected.confidence}</strong><small>结构可信度</small></div>
      </div>
      <div className="setup-ribbon">
        <span><Layers3 size={14} />{selected.title}</span>
        <span><Clock3 size={14} />{selected.state === "ENTRY_VALID" ? "有效窗口开启" : "等待触发"}</span>
        <span className="data-fresh"><CheckCircle2 size={14} />{mode === "live" && candles.length ? "实时 K 线" : "图表数据不可用"}</span>
      </div>
      <div className="chart-shell">
        {mode === "live" && candles.length ? <MiniChart selected={selected} candles={candles} /> : <div className="chart-unavailable"><AlertTriangle size={20} /><strong>暂无可验证的实时 K 线</strong><span>不会用模拟走势替代真实行情</span></div>}
        <div className="chart-watermark">{mode === "live" && candles.length ? "5m · BYBIT PUBLIC" : "NO MARKET DATA"}</div>
      </div>
      <section className="evidence-panel">
        <div className="section-title"><div><span className="eyebrow">WHY NOW</span><h3>核心证据</h3></div><button>展开原始数据</button></div>
        <div className="evidence-grid">
          {selected.evidence.slice(0, 3).map((item, index) => (
            <article key={item.code}><span>0{index + 1}</span><div><strong>{item.text}</strong><small>{item.value ? `实时值 ${item.value}` : "多源数据已确认"}</small></div><CheckCircle2 size={17} /></article>
          ))}
        </div>
        {selected.risk && <div className="risk-line"><AlertTriangle size={15} /><strong>主要风险</strong><span>{selected.risk}</span></div>}
      </section>
    </main>
  );
}

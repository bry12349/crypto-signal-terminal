import { useEffect, useMemo, useRef, useState } from "react";
import { CandlestickSeries, ColorType, createChart, HistogramSeries, LineSeries, type IChartApi, type ISeriesApi, type Time, type UTCTimestamp } from "lightweight-charts";
import { AlertTriangle, CheckCircle2, Clock3, Crosshair, Layers3 } from "lucide-react";

import { formatBeijingDateTime, formatBeijingTime, type ChartBar } from "../chartController";
import type { Candle, MarketSymbolHealth, Opportunity } from "../types";

// Bitget's documented default follows the international convention: green up, red down.
const candleColors = () => ({ up: getComputedStyle(document.documentElement).getPropertyValue("--candle-up").trim() || "#2f8cff", down: getComputedStyle(document.documentElement).getPropertyValue("--candle-down").trim() || "#f6465d" });
const TIMEFRAMES = [{ label: "5m", interval: "5" }, { label: "15m", interval: "15" }, { label: "1h", interval: "60" }, { label: "4h", interval: "240" }] as const;
type Timeframe = typeof TIMEFRAMES[number]["label"];
type PrimaryIndicator = "NONE" | "MA" | "EMA" | "EMA26" | "VWAP" | "BOLL";
type SecondaryIndicator = "VOLUME" | "RSI" | "MACD" | "CVD" | "OI" | "FUNDING";
type DerivativesHistory = { open_interest: { time: number; value: string }[]; funding: { time: number; value: string }[] };

const toBars = (candles: Candle[]): ChartBar[] => candles.map((item) => ({ time: item.timestamp, open: +item.open, high: +item.high, low: +item.low, close: +item.close, volume: +item.volume }));

function movingAverage(bars: ChartBar[], period: number, exponential = false) {
  let previous = 0;
  return bars.map((bar, index) => {
    if (index + 1 < period) return null;
    const value = exponential
      ? (previous = previous ? bar.close * (2 / (period + 1)) + previous * (1 - 2 / (period + 1)) : bars.slice(0, period).reduce((sum, item) => sum + item.close, 0) / period)
      : bars.slice(index - period + 1, index + 1).reduce((sum, item) => sum + item.close, 0) / period;
    return { time: bar.time as UTCTimestamp, value };
  }).filter((item): item is { time: UTCTimestamp; value: number } => item !== null);
}

function bollingerBands(bars: ChartBar[], period = 20) {
  const upper: { time: UTCTimestamp; value: number }[] = [];
  const middle: { time: UTCTimestamp; value: number }[] = [];
  const lower: { time: UTCTimestamp; value: number }[] = [];
  bars.forEach((bar, index) => {
    if (index + 1 < period) return;
    const sample = bars.slice(index - period + 1, index + 1).map((item) => item.close);
    const mean = sample.reduce((sum, value) => sum + value, 0) / sample.length;
    const deviation = Math.sqrt(sample.reduce((sum, value) => sum + (value - mean) ** 2, 0) / sample.length);
    const time = bar.time as UTCTimestamp;
    upper.push({ time, value: mean + deviation * 2 }); middle.push({ time, value: mean }); lower.push({ time, value: mean - deviation * 2 });
  });
  return [upper, middle, lower];
}

function rsiData(bars: ChartBar[]) {
  return bars.map((bar, index) => {
    const window = bars.slice(Math.max(1, index - 13), index + 1);
    if (window.length < 2) return null;
    const changes = window.slice(1).map((item, offset) => item.close - window[offset].close);
    const gain = changes.reduce((sum, value) => sum + Math.max(value, 0), 0) / changes.length;
    const loss = changes.reduce((sum, value) => sum + Math.max(-value, 0), 0) / changes.length;
    return { time: bar.time as UTCTimestamp, value: loss === 0 ? 100 : 100 - 100 / (1 + gain / loss) };
  }).filter((item): item is { time: UTCTimestamp; value: number } => item !== null);
}

function macdData(bars: ChartBar[]) {
  return bars.map((bar, index) => {
    const fast = movingAverage(bars.slice(0, index + 1), 7, true).at(-1)?.value;
    const slow = movingAverage(bars.slice(0, index + 1), 14, true).at(-1)?.value;
    return fast === undefined || slow === undefined ? null : { time: bar.time as UTCTimestamp, value: fast - slow, color: fast >= slow ? "rgba(14, 203, 129, .65)" : "rgba(246, 70, 93, .65)" };
  }).filter((item): item is { time: UTCTimestamp; value: number; color: string } => item !== null);
}

function cvdData(bars: ChartBar[]) {
  let total = 0;
  return bars.map((bar) => {
    total += bar.close >= bar.open ? bar.volume : -bar.volume;
    return { time: bar.time as UTCTimestamp, value: total };
  });
}

function vwapData(bars: ChartBar[]) {
  let volume = 0; let weighted = 0;
  return bars.map((bar) => {
    const typical = (bar.high + bar.low + bar.close) / 3;
    volume += bar.volume; weighted += typical * bar.volume;
    return { time: bar.time as UTCTimestamp, value: volume ? weighted / volume : typical };
  });
}

function MiniChart({ selected, marketSymbol, candles, timeframe, primary, secondary, derivatives }: { selected: Opportunity; marketSymbol: string; candles: Candle[]; timeframe: Timeframe; primary: PrimaryIndicator; secondary: SecondaryIndicator; derivatives: DerivativesHistory | null }) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candle = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const viewKey = useRef<string | null>(null);
  const chartDestroyed = useRef(false);
  const data = useMemo(() => toBars(candles), [candles]);

  useEffect(() => {
    if (!host.current) return;
    chartDestroyed.current = false;
    const instance = createChart(host.current, {
      width: host.current.clientWidth, height: host.current.clientHeight,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#718096", fontFamily: "IBM Plex Mono, monospace" },
      localization: { timeFormatter: (time: Time) => formatBeijingDateTime(time as number) },
      grid: { vertLines: { color: "rgba(52, 69, 91, .18)" }, horzLines: { color: "rgba(52, 69, 91, .18)" } },
      timeScale: { timeVisible: true, secondsVisible: false, tickMarkFormatter: (time: Time) => formatBeijingTime(typeof time === "number" ? time : 0) },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false }, handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    });
    const colors = candleColors();
    const candleSeries = instance.addSeries(CandlestickSeries, { upColor: colors.up, downColor: colors.down, wickUpColor: colors.up, wickDownColor: colors.down, borderVisible: false });
    const subPane = instance.addPane(true);
    subPane.setHeight(108);
    const volumeSeries = instance.addSeries(HistogramSeries, { priceFormat: { type: "volume" } }, 1);
    chart.current = instance; candle.current = candleSeries; volume.current = volumeSeries;
    const resize = new ResizeObserver(([entry]) => instance.applyOptions({ width: entry.contentRect.width, height: entry.contentRect.height }));
    resize.observe(host.current); return () => {
      // React StrictMode tears down the chart effect before indicator effects.
      // Make their later cleanup a no-op instead of passing stale series back to
      // lightweight-charts, which throws "Value is undefined".
      chartDestroyed.current = true;
      chart.current = null; candle.current = null; volume.current = null;
      resize.disconnect(); instance.remove();
    };
  }, []);

  useEffect(() => {
    if (!data.length) return;
    // Each selected period is a separate asynchronous snapshot. Replacing the
    // full series is essential: an incremental update only changes the last
    // candle and would leave the previous timeframe visible.
    candle.current?.setData(data.map(({ volume: _volume, ...bar }) => ({ ...bar, time: bar.time as UTCTimestamp })));
    const nextViewKey = `${selected.id}:${marketSymbol}:${timeframe}`;
    if (viewKey.current !== nextViewKey) { viewKey.current = nextViewKey; chart.current?.timeScale().fitContent(); }
    chart.current?.timeScale().scrollToRealTime();
  }, [data, marketSymbol, timeframe]);

  useEffect(() => {
    if (!chart.current) return;
    const old = volume.current;
    if (old) chart.current.removeSeries(old);
    const series = secondary === "VOLUME"
      ? chart.current.addSeries(HistogramSeries, { priceFormat: { type: "volume" } }, 1)
      : chart.current.addSeries(LineSeries, { color: secondary === "RSI" ? "#d7a84e" : secondary === "OI" ? "#5aa9ff" : secondary === "FUNDING" ? "#f7b955" : "#b58cff", lineWidth: 1, lastValueVisible: true, priceLineVisible: false }, 1);
    volume.current = series as ISeriesApi<"Histogram">;
    if (secondary === "VOLUME") { const colors = candleColors(); (series as ISeriesApi<"Histogram">).setData(data.map((bar) => ({ time: bar.time as UTCTimestamp, value: bar.volume, color: bar.close >= bar.open ? `${colors.up}80` : `${colors.down}80` }))); }
    else if (secondary === "RSI") (series as ISeriesApi<"Line">).setData(rsiData(data));
    else if (secondary === "MACD") (series as ISeriesApi<"Line">).setData(macdData(data));
    else if (secondary === "CVD") (series as ISeriesApi<"Line">).setData(cvdData(data));
    else {
      const points = secondary === "OI" ? derivatives?.open_interest : derivatives?.funding;
      (series as ISeriesApi<"Line">).setData((points ?? []).map((point) => ({ time: point.time as UTCTimestamp, value: Number(point.value) })));
    }
    return () => { if (!chartDestroyed.current && chart.current) chart.current.removeSeries(series); if (volume.current === series) volume.current = null; };
  }, [data, derivatives, secondary]);

  useEffect(() => {
    if (!chart.current || primary === "NONE") return;
    const settings = { lineWidth: 1 as const, lastValueVisible: false, priceLineVisible: false };
    if (primary === "BOLL") {
      const lines = ["#9b8cff", "#d7a84e", "#9b8cff"].map((color) => chart.current!.addSeries(LineSeries, { ...settings, color }));
      bollingerBands(data).forEach((band, index) => lines[index].setData(band));
      return () => { if (!chartDestroyed.current) lines.forEach((line) => chart.current?.removeSeries(line)); };
    }
    const line = chart.current.addSeries(LineSeries, { ...settings, color: primary === "EMA" || primary === "EMA26" ? "#f7b955" : primary === "VWAP" ? "#d7a84e" : "#38bdf8" });
    line.setData(primary === "VWAP" ? vwapData(data) : movingAverage(data, primary === "EMA26" ? 26 : primary === "EMA" ? 12 : 20, primary === "EMA" || primary === "EMA26"));
    return () => { if (!chartDestroyed.current) chart.current?.removeSeries(line); };
  }, [data, primary]);

  useEffect(() => {
    if (!candle.current || !selected.order_plan) return;
    const series = candle.current;
    const colors = candleColors();
    const stop = series.createPriceLine({ price: +selected.order_plan.stop, color: colors.down, lineWidth: 1, lineStyle: 2, title: "SL" });
    const targets = selected.order_plan.targets.map((target, index) => series.createPriceLine({ price: +target, color: colors.up, lineWidth: 1, lineStyle: 2, title: `TP${index + 1}` }));
    return () => { if (!chartDestroyed.current) { series.removePriceLine(stop); targets.forEach((line) => series.removePriceLine(line)); } };
  }, [selected]);

  return <div className="chart" ref={host} aria-label={`北京时间 ${timeframe} K 线图`} />;
}

function AnalysisStrip({ selected }: { selected: Opportunity }) {
  const analysis = selected.analysis;
  if (!analysis) return null;
  const decision = analysis.decision;
  const passed = decision?.gates.filter((gate) => gate.passed).length ?? 0;
  const calibrationText = analysis.calibration?.status === "VALIDATED"
    ? `历史校准：已验证（${analysis.calibration.settled} 笔已结算）`
    : analysis.calibration?.status === "DEGRADED"
      ? `历史校准：偏差超限（${analysis.calibration.settled} 笔已结算）`
      : analysis.calibration ? `历史校准：样本不足（${analysis.calibration.settled} 笔已结算，不宣称胜率）` : null;
  return <><div className="analysis-strip"><span><small>EDGE</small><strong>{analysis.opportunity_score}</strong></span><span><small>P(TP&gt;SL)</small><strong>{(Number(analysis.p_tp_before_sl) * 100).toFixed(1)}%</strong></span><span><small>EV</small><strong className={Number(analysis.expected_value) > 0 ? "positive" : "negative"}>{analysis.expected_value}</strong></span><span><small>{analysis.market_regime}</small><strong>{analysis.signal_type}</strong></span><div className="analysis-biases"><span>SMART {analysis.smart_money_bias}</span><span>DERIVATIVES {analysis.derivatives_bias}</span><span>FLOW {analysis.order_flow_bias}</span><span>NEWS {analysis.news_bias}</span></div></div>{decision && <div className={`decision-panel ${decision.outcome.toLowerCase()}`}><strong>{decision.outcome === "TRADE" ? "可交易" : "暂不交易"} · {passed}/{decision.gates.length} 门槛通过</strong><div>{decision.gates.map((gate) => <span key={gate.key} aria-label={gate.label} className={gate.passed ? "passed" : "blocked"}>{gate.passed ? "✓" : "×"} {gate.label}</span>)}</div>{calibrationText && <small className="calibration-note">{calibrationText}</small>}</div>}</>;
}

export function SignalCanvas({ selected, candles, mode, health }: { selected: Opportunity | null; candles: Candle[]; mode: string; health: MarketSymbolHealth | undefined }) {
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [primary, setPrimary] = useState<PrimaryIndicator>("MA");
  const [secondary, setSecondary] = useState<SecondaryIndicator>("VOLUME");
  const [periodCandles, setPeriodCandles] = useState<Candle[] | null>(null);
  const [derivatives, setDerivatives] = useState<DerivativesHistory | null>(null);
  const [periodLoading, setPeriodLoading] = useState(false);
  const [appearanceVersion, setAppearanceVersion] = useState(0);
  const marketSymbol = selected?.market_symbol ?? selected?.symbol ?? "BTCUSDT";
  const onchainTokenAddress = selected?.onchain_token_address ?? null;
  const isOnchainChart = Boolean(onchainTokenAddress);
  useEffect(() => { const refresh = () => setAppearanceVersion((value) => value + 1); window.addEventListener("appearance-change", refresh); return () => window.removeEventListener("appearance-change", refresh); }, []);
  useEffect(() => {
    if (!selected || mode !== "live") return;
    const abort = new AbortController();
    const interval = TIMEFRAMES.find((item) => item.label === timeframe)!.interval;
    // Only a user-selected symbol/period change may clear the chart. Market
    // snapshots replace `candles` every five seconds, and clearing here on
    // each replacement caused a visible chart flash before the next response.
    setPeriodCandles([]);
    setDerivatives(null);
    setPeriodLoading(true);
    const refresh = () => {
      fetch(onchainTokenAddress
        ? `http://127.0.0.1:8765/api/v1/onchain/bsc/${encodeURIComponent(onchainTokenAddress)}/candles?interval=${interval}`
        : `http://127.0.0.1:8765/api/v1/markets/${encodeURIComponent(marketSymbol)}/candles?interval=${interval}`, { signal: abort.signal })
        .then((response) => response.ok ? response.json() as Promise<Candle[]> : Promise.reject(new Error("candle source unavailable")))
        .then((values) => { if (!abort.signal.aborted) setPeriodCandles(values); })
        .catch(() => { if (!abort.signal.aborted) setPeriodCandles(timeframe === "5m" ? candles : []); })
        .finally(() => { if (!abort.signal.aborted) setPeriodLoading(false); });
    };
    refresh();
    if (!onchainTokenAddress) fetch(`http://127.0.0.1:8765/api/v1/markets/${encodeURIComponent(marketSymbol)}/derivatives?interval=${interval}`, { signal: abort.signal })
      .then((response) => response.ok ? response.json() as Promise<DerivativesHistory> : Promise.reject(new Error("derivatives source unavailable")))
      .then((values) => { if (!abort.signal.aborted) setDerivatives(values); })
      .catch(() => { if (!abort.signal.aborted) setDerivatives(null); });
    const poll = window.setInterval(refresh, 5000);
    return () => { abort.abort(); window.clearInterval(poll); };
  }, [marketSymbol, mode, onchainTokenAddress, selected?.id, timeframe]);
  if (!selected) return <main className="signal-canvas empty-canvas"><Crosshair size={26} /><h2>当前无可执行机会</h2><p>只有满足触发、流动性与风控条件的结构才会出现在这里。</p></main>;
  const direction = selected.order_plan?.direction; const base = isOnchainChart ? selected.symbol : marketSymbol.replace("USDT", "");
  const isWalletFlow = selected.source === "SMART_MONEY" && Boolean(selected.source_label);
  const healthLabel = isOnchainChart ? `${base} 链上池行情` : health?.status === "healthy" ? `${base} 行情健康` : health?.status === "degraded" ? `${base} 行情降级` : health?.status === "unavailable" ? `${base} 行情不可用` : `${base} 行情待确认`;
  return <main className="signal-canvas"><div className="instrument-head"><div><span className="eyebrow">SELECTED INSTRUMENT · UTC+8</span><h1>{base}<small>{isOnchainChart ? " / BSC DEX" : " / USDT PERP"}</small></h1></div><div className={`direction-lock ${direction?.toLowerCase() ?? "watch"}`}><span>{direction ?? "NO TRADE"}</span><strong>{selected.confidence}</strong><small>{selected.state === "FORMING" ? "观察强度" : "结构可信度"}</small></div></div>
    <div className="setup-ribbon"><span><Layers3 size={14} />{selected.title}</span><span><Clock3 size={14} />{selected.state === "ENTRY_VALID" ? "有效窗口开启" : "等待触发"}</span><span className={`data-fresh ${!isOnchainChart && health?.status !== "healthy" ? "unhealthy" : ""}`}>{isOnchainChart || health?.status === "healthy" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}{healthLabel}</span></div>
    <div className="chart-shell"><div className="chart-toolbar"><div className="timeframe-group" aria-label="K线周期">{TIMEFRAMES.map((item) => <button type="button" key={item.label} aria-pressed={timeframe === item.label} className={timeframe === item.label ? "active" : ""} onPointerDown={(event) => event.stopPropagation()} onClick={() => setTimeframe(item.label)}>{item.label}</button>)}</div><label>主图指标<select aria-label="主图指标" value={primary} onPointerDown={(event) => event.stopPropagation()} onChange={(event) => setPrimary(event.target.value as PrimaryIndicator)}><option value="NONE">无</option><option value="MA">MA20</option><option value="EMA">EMA12</option><option value="EMA26">EMA26</option><option value="VWAP">VWAP</option><option value="BOLL">BOLL20</option></select></label><label>副图指标<select aria-label="副图指标" value={secondary} onPointerDown={(event) => event.stopPropagation()} onChange={(event) => setSecondary(event.target.value as SecondaryIndicator)}><option value="VOLUME">VOL</option><option value="RSI">RSI14</option><option value="MACD">MACD</option><option value="CVD">CVD（成交方向代理）</option>{!isOnchainChart && <><option value="OI">OI</option><option value="FUNDING">资金费率</option></>}</select></label></div>{mode === "live" && (periodCandles ?? candles).length ? <MiniChart key={appearanceVersion} selected={selected} marketSymbol={isOnchainChart ? selected.symbol : marketSymbol} candles={periodCandles ?? candles} timeframe={timeframe} primary={primary} secondary={secondary} derivatives={derivatives} /> : <div className="chart-unavailable"><AlertTriangle size={20} /><strong>{periodLoading && (isOnchainChart || candles.length) ? `正在加载 ${timeframe} ${isOnchainChart ? "链上" : "实时"} K 线` : `暂无可验证的${isOnchainChart ? "链上" : "实时"} K 线`}</strong><span>不会用模拟走势替代真实行情</span></div>}<div className="chart-watermark">{mode === "live" && (periodCandles ?? candles).length ? `${timeframe} · ${isOnchainChart ? "BSC DEX OHLCV" : "PUBLIC FUTURES"} · UTC+8` : "NO MARKET DATA"}</div></div>
    <section className="evidence-panel">{isWalletFlow && <div className="wallet-flow-summary"><div><span className="eyebrow">ON-CHAIN SMART MONEY</span><h3>钱包流向详情</h3></div><span className="wallet-market-benchmark">{isOnchainChart ? `链上池 · ${base} / BSC` : `市场基准 · ${base}/USDT`}</span><p>{selected.source_label}</p><small>{isOnchainChart ? "K 线来自 BSC DEX 的公开流动性池；钱包活动不等同于中心化交易所的合约开仓。" : "当前 K 线仅用于市场环境确认；钱包活动不等同于中心化交易所的合约开仓。"}</small></div>}<AnalysisStrip selected={selected} /><div className="section-title"><div><span className="eyebrow">WHY NOW</span><h3>核心证据</h3></div></div><div className="evidence-grid">{selected.evidence.slice(0, 3).map((item, index) => <article key={item.code}><span>0{index + 1}</span><div><strong>{item.text}</strong><small>{item.value ? `实时值 ${item.value}` : "多源数据已确认"}</small></div><CheckCircle2 size={17} /></article>)}</div>{selected.risk && <div className="risk-line"><AlertTriangle size={15} /><strong>主要风险</strong><span>{selected.risk}</span></div>}</section></main>;
}

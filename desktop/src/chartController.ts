export interface ChartBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IncrementalSeries {
  setData: (bars: ChartBar[]) => void;
  update: (bar: ChartBar) => void;
}

export type BusinessDayLike = { year: number; month: number; day: number };

export function toUnixTimestamp(time: number | string | BusinessDayLike): number {
  if (typeof time === "number") return time;
  if (typeof time === "string") return Math.floor(new Date(`${time}T00:00:00Z`).getTime() / 1000);
  return Math.floor(Date.UTC(time.year, time.month - 1, time.day) / 1000);
}

const BEIJING_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Shanghai",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatBeijingTime(timestamp: number): string {
  return BEIJING_TIME.format(new Date(timestamp * 1000));
}

const BEIJING_DATE_TIME = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hour12: false,
});

export function formatBeijingDateTime(time: number | string | BusinessDayLike): string {
  return BEIJING_DATE_TIME.format(new Date(toUnixTimestamp(time) * 1000));
}

export function aggregateBars(bars: ChartBar[], factor: number): ChartBar[] {
  if (factor <= 1) return bars;
  const result: ChartBar[] = [];
  for (let index = 0; index < bars.length; index += factor) {
    const group = bars.slice(index, index + factor);
    if (!group.length) continue;
    result.push({ time: group[0].time, open: group[0].open, high: Math.max(...group.map((bar) => bar.high),), low: Math.min(...group.map((bar) => bar.low),), close: group.at(-1)!.close, volume: group.reduce((total, bar) => total + bar.volume, 0) });
  }
  return result;
}

export function createIncrementalSeriesUpdater(series: IncrementalSeries) {
  let activeSymbol: string | null = null;

  return {
    sync(symbol: string, bars: ChartBar[]) {
      if (activeSymbol !== symbol) {
        activeSymbol = symbol;
        series.setData(bars);
        return;
      }
      const latest = bars.at(-1);
      if (latest) series.update(latest);
    },
  };
}

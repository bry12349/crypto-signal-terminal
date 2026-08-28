import { Palette } from "lucide-react";
import { useEffect, useState } from "react";

type Theme = "dark" | "paper" | "bitget";
type CandlePalette = "bitget" | "international" | "cn";

export function AppearanceControls() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("cst-theme");
    return saved === "light" ? "paper" : saved === "bitget" || saved === "paper" ? saved : "dark";
  });
  const [candles, setCandles] = useState<CandlePalette>(() => (localStorage.getItem("cst-candles") as CandlePalette) || "bitget");
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("cst-theme", theme); window.dispatchEvent(new Event("appearance-change")); }, [theme]);
  useEffect(() => { document.documentElement.dataset.candles = candles; localStorage.setItem("cst-candles", candles); window.dispatchEvent(new Event("appearance-change")); }, [candles]);
  return <div className="appearance-controls"><Palette size={14} /><select aria-label="软件主题" value={theme} onChange={(event) => setTheme(event.target.value as Theme)}><option value="dark">石墨深色</option><option value="bitget">Bitget 海军蓝</option><option value="paper">纸墨柔光</option></select><select aria-label="K线颜色" value={candles} onChange={(event) => setCandles(event.target.value as CandlePalette)}><option value="bitget">蓝涨红跌</option><option value="international">绿涨红跌</option><option value="cn">红涨绿跌</option></select></div>;
}

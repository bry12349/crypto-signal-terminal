import { describe, expect, it } from "vitest";

import styles from "./styles.css?raw";

describe("terminal layout", () => {
  it("reserves the wheel for the chart instead of making its parent scroll", () => {
    expect(styles).toContain("grid-template: 48px minmax(0, 1fr) 28px / 56px 1fr");
    expect(styles).toContain(".workspace, .opportunity-rail, .order-panel { min-height: 0; }");
    expect(styles).toContain(".opportunity-list { flex: 1; min-height: 0; }");
    expect(styles).toContain(".signal-canvas { overflow: hidden; }");
    expect(styles).toContain(".chart-shell { overflow: hidden; }");
    expect(styles).toMatch(/grid-template-rows:\s*74px 36px minmax\(0,\s*1fr\) auto;/);
  });

  it("defines distinct low-glare palettes for dark, Bitget dark, and paper themes", () => {
    expect(styles).toContain(':root[data-theme="bitget"] { --accent: #2f8cff; --surface: #111a2b;');
    expect(styles).toContain(':root[data-theme="paper"] {');
    expect(styles).not.toContain(':root[data-theme="light"]');
  });
});

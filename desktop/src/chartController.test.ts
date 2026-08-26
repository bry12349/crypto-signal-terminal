import { describe, expect, it, vi } from "vitest";

import { createIncrementalSeriesUpdater, formatBeijingDateTime, formatBeijingTime, toUnixTimestamp } from "./chartController";

describe("createIncrementalSeriesUpdater", () => {
  it("replaces data only when the symbol changes and incrementally updates the active candle", () => {
    const setData = vi.fn();
    const update = vi.fn();
    const updater = createIncrementalSeriesUpdater({ setData, update });
    const btc = [{ time: 1, open: 100, high: 101, low: 99, close: 100, volume: 10 }];
    const nextBtc = [{ time: 1, open: 100, high: 102, low: 99, close: 101, volume: 11 }];

    updater.sync("BTCUSDT", btc);
    updater.sync("BTCUSDT", nextBtc);

    expect(setData).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledWith(nextBtc[0]);
  });
});

describe("formatBeijingTime", () => {
  it("renders chart timestamps in Beijing time", () => {
    expect(formatBeijingTime(0)).toBe("08:00");
    expect(formatBeijingDateTime(0)).toContain("1970");
  });

  it("normalizes Lightweight Charts business-day values before formatting", () => {
    expect(toUnixTimestamp({ year: 1970, month: 1, day: 1 })).toBe(0);
  });
});

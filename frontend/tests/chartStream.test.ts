import { describe, expect, it } from "vitest";
import { mergeFormingCandle } from "../src/services/chartStream";

const candle = (time: string, completed: boolean) => ({
  open_time_utc: time, open: 1, high: 2, low: 1, close: 2, tick_volume: 1, completed,
});

describe("forming candle stream", () => {
  it("updates the current forming bar without changing its history length", () => {
    const previous = [candle("2026-11-13T00:00:00Z", true), candle("2026-11-13T00:05:00Z", false)];
    const next = mergeFormingCandle(previous, { ...previous[1], close: 1.5 });
    expect(next).toHaveLength(2);
    expect(next[1].close).toBe(1.5);
  });

  it("appends a new bar without losing the latest completed candle", () => {
    const previous = [candle("2026-11-13T00:00:00Z", true), candle("2026-11-13T00:05:00Z", true)];
    const next = mergeFormingCandle(previous, candle("2026-11-13T00:10:00Z", false));
    expect(next.map((bar) => bar.open_time_utc)).toEqual([
      "2026-11-13T00:00:00Z", "2026-11-13T00:05:00Z", "2026-11-13T00:10:00Z",
    ]);
  });

  it("ignores delayed bar updates", () => {
    const previous = [candle("2026-11-13T00:05:00Z", true)];
    expect(mergeFormingCandle(previous, candle("2026-11-13T00:00:00Z", false))).toEqual(previous);
  });
});

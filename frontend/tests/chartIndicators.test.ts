import { describe, expect, it } from "vitest";
import { bollingerSeries, completedCandles, emaSeries, indicatorReadings, tickActivitySeries, tickActivityVwap } from "../src/services/chartIndicators";
import { defaultViewportRange } from "../src/services/chartViewport";
import type { Candle } from "../src/types/api";

function candle(index: number, completed = true): Candle {
  const open = 4000 + index;
  return {
    open_time_utc: new Date(Date.UTC(2026, 9, 20, 0, index * 5)).toISOString(),
    open,
    high: open + 2,
    low: open - 1,
    close: open + 1,
    tick_volume: 10 + index,
    completed,
  };
}

describe("chart indicators", () => {
  it("uses a focused M5 viewport by default while keeping room beyond the latest candle", () => {
    expect(defaultViewportRange(289)).toEqual({ from: 208, to: 316 });
    expect(defaultViewportRange(50)).toEqual({ from: 0, to: 77 });
  });

  it("uses only completed broker candles for derived overlays and readings", () => {
    const candles = [...Array.from({ length: 21 }, (_, index) => candle(index)), { ...candle(22, false), close: 9999, tick_volume: 9999 }];

    expect(completedCandles(candles)).toHaveLength(21);
    expect(emaSeries(candles, 20)).toHaveLength(2);
    expect(bollingerSeries(candles)).toMatchObject({ upper: expect.any(Array), lower: expect.any(Array) });
    expect(bollingerSeries(candles).upper).toHaveLength(2);
    expect(tickActivityVwap(candles)).toHaveLength(21);
    expect(tickActivitySeries(candles)).toHaveLength(21);
    expect(indicatorReadings(candles).ema20).toBeLessThan(4100);
  });

  it("labels absent history as unavailable instead of manufacturing an indicator", () => {
    const readings = indicatorReadings([candle(1)]);

    expect(readings.ema20).toBeNull();
    expect(readings.ema60).toBeNull();
    expect(readings.rsi14).toBeNull();
    expect(readings.atr14).toBeNull();
  });
});

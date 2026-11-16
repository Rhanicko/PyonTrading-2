import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { bollingerSeries, completedCandles, emaSeries, indicatorReadings, tickActivitySeries, tickActivityVwapSessions } from "../src/services/chartIndicators";
import { chartViewportStorageKey, defaultViewportRange, legacyViewportStorageKey, loadViewport } from "../src/services/chartViewport";
import type { Candle } from "../src/types/api";

const goldenFixture = JSON.parse(readFileSync(resolve(process.cwd(), "..", "fixtures", "technical-golden.json"), "utf8")) as {
  candles: Candle[];
  expected: { completed_count: number; rsi_14: number; atr_14: number };
};

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
  it("breaks the VWAP line when its UTC session resets", () => {
    const sessions = tickActivityVwapSessions([candle(287), candle(288), candle(289)]);
    expect(sessions).toHaveLength(2);
    expect(sessions[0]).toHaveLength(1);
    expect(sessions[1]).toHaveLength(2);
    expect(sessions[0][0]).toHaveProperty("value");
    expect(sessions[1][0]).toHaveProperty("value");
  });
  it("uses a focused M5 viewport by default while keeping room beyond the latest candle", () => {
    expect(defaultViewportRange(289)).toEqual({ from: 208, to: 316 });
    expect(defaultViewportRange(50)).toEqual({ from: 0, to: 77 });
  });

  it("scopes saved chart viewports by exact broker, symbol, and timeframe", () => {
    expect(chartViewportStorageKey({ brokerServer: "MetaQuotes-Demo", symbol: "XAUUSD", timeframe: "M5" }))
      .not.toBe(chartViewportStorageKey({ brokerServer: "MetaQuotes-Demo", symbol: "XAUUSDm", timeframe: "M5" }));
    expect(chartViewportStorageKey({ brokerServer: "MetaQuotes-Demo", symbol: "XAUUSD", timeframe: "M5" }))
      .not.toBe(chartViewportStorageKey({ brokerServer: "AnotherBroker-Live", symbol: "XAUUSD", timeframe: "M5" }));
  });

  it("migrates a legacy XAUUSD viewport to its broker-scoped key without using it for a different exact symbol", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => void values.set(key, value),
      removeItem: (key: string) => void values.delete(key),
    };
    const xauusd = { brokerServer: "MetaQuotes-Demo", symbol: "XAUUSD", timeframe: "M5" };
    const legacy = { from: 42, to: 90 };
    storage.setItem(legacyViewportStorageKey("M5"), JSON.stringify(legacy));

    expect(loadViewport(storage, xauusd)).toEqual(legacy);
    expect(storage.getItem(chartViewportStorageKey(xauusd))).toBe(JSON.stringify(legacy));
    expect(loadViewport(storage, { ...xauusd, symbol: "XAUUSDm" })).toBeNull();
  });

  it("uses only completed broker candles for derived overlays and readings", () => {
    const candles = [...Array.from({ length: 21 }, (_, index) => candle(index)), { ...candle(22, false), close: 9999, tick_volume: 9999 }];

    expect(completedCandles(candles)).toHaveLength(21);
    expect(emaSeries(candles, 20)).toHaveLength(2);
    expect(bollingerSeries(candles)).toMatchObject({ upper: expect.any(Array), lower: expect.any(Array) });
    expect(bollingerSeries(candles).upper).toHaveLength(2);
    expect(tickActivityVwapSessions(candles).flat()).toHaveLength(21);
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

  it("matches the backend Wilder RSI and ATR contract for completed golden candles", () => {
    const readings = indicatorReadings(goldenFixture.candles);

    expect(completedCandles(goldenFixture.candles)).toHaveLength(goldenFixture.expected.completed_count);
    expect(readings.rsi14).toBeCloseTo(goldenFixture.expected.rsi_14, 12);
    expect(readings.atr14).toBeCloseTo(goldenFixture.expected.atr_14, 12);
  });
});

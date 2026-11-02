import type { UTCTimestamp } from "lightweight-charts";
import type { Candle } from "../types/api";

export type IndicatorPoint = { time: UTCTimestamp; value: number };
export type ActivityPoint = IndicatorPoint & { color: string };

function timeOf(candle: Candle): UTCTimestamp {
  return Math.floor(new Date(candle.open_time_utc).getTime() / 1000) as UTCTimestamp;
}

export function completedCandles(candles: Candle[]): Candle[] {
  return candles.filter((candle) => candle.completed);
}

function emaValues(values: number[], period: number): Array<number | null> {
  const result = Array<number | null>(values.length).fill(null);
  if (values.length < period) return result;
  const multiplier = 2 / (period + 1);
  let current = values.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  result[period - 1] = current;
  for (let index = period; index < values.length; index += 1) {
    current = (values[index] - current) * multiplier + current;
    result[index] = current;
  }
  return result;
}

export function emaSeries(candles: Candle[], period: number): IndicatorPoint[] {
  const completed = completedCandles(candles);
  const values = emaValues(completed.map((candle) => candle.close), period);
  return completed.flatMap((candle, index) => values[index] === null ? [] : [{ time: timeOf(candle), value: values[index] }]);
}

export function bollingerSeries(candles: Candle[], period = 20, deviations = 2): { upper: IndicatorPoint[]; lower: IndicatorPoint[] } {
  const completed = completedCandles(candles);
  const upper: IndicatorPoint[] = [];
  const lower: IndicatorPoint[] = [];
  for (let index = period - 1; index < completed.length; index += 1) {
    const window = completed.slice(index - period + 1, index + 1).map((candle) => candle.close);
    const average = window.reduce((sum, value) => sum + value, 0) / period;
    const standardDeviation = Math.sqrt(window.reduce((sum, value) => sum + (value - average) ** 2, 0) / period);
    upper.push({ time: timeOf(completed[index]), value: average + deviations * standardDeviation });
    lower.push({ time: timeOf(completed[index]), value: average - deviations * standardDeviation });
  }
  return { upper, lower };
}

export function tickActivityVwap(candles: Candle[]): IndicatorPoint[] {
  let session = "";
  let weightedPrice = 0;
  let activity = 0;
  return completedCandles(candles).flatMap((candle) => {
    const nextSession = candle.open_time_utc.slice(0, 10);
    if (nextSession !== session) {
      session = nextSession;
      weightedPrice = 0;
      activity = 0;
    }
    const weight = Math.max(candle.tick_volume, 0);
    if (!weight) return [];
    weightedPrice += ((candle.high + candle.low + candle.close) / 3) * weight;
    activity += weight;
    return [{ time: timeOf(candle), value: weightedPrice / activity }];
  });
}

export function tickActivitySeries(candles: Candle[]): ActivityPoint[] {
  return completedCandles(candles).map((candle) => ({
    time: timeOf(candle),
    value: Math.max(candle.tick_volume, 0),
    color: candle.close >= candle.open ? "rgba(94, 227, 174, .62)" : "rgba(255, 130, 120, .62)",
  }));
}

export interface IndicatorReadings {
  ema20: number | null;
  ema60: number | null;
  rsi14: number | null;
  atr14: number | null;
  relativeActivity: number | null;
}

function latest(values: IndicatorPoint[]): number | null {
  return values.at(-1)?.value ?? null;
}

function rsi(values: number[], period = 14): number | null {
  if (values.length <= period) return null;
  const changes = values.slice(1).map((value, index) => value - values[index]);
  const window = changes.slice(-period);
  const gain = window.filter((value) => value > 0).reduce((sum, value) => sum + value, 0) / period;
  const loss = Math.abs(window.filter((value) => value < 0).reduce((sum, value) => sum + value, 0)) / period;
  if (!loss) return gain ? 100 : 50;
  return 100 - 100 / (1 + gain / loss);
}

function atr(candles: Candle[], period = 14): number | null {
  if (candles.length <= period) return null;
  const ranges = candles.slice(1).map((candle, index) => Math.max(
    candle.high - candle.low,
    Math.abs(candle.high - candles[index].close),
    Math.abs(candle.low - candles[index].close),
  ));
  return ranges.slice(-period).reduce((sum, value) => sum + value, 0) / period;
}

export function indicatorReadings(candles: Candle[]): IndicatorReadings {
  const completed = completedCandles(candles);
  const activity = completed.map((candle) => Math.max(candle.tick_volume, 0));
  const recentActivity = activity.slice(-20);
  const averageActivity = recentActivity.length ? recentActivity.reduce((sum, value) => sum + value, 0) / recentActivity.length : 0;
  return {
    ema20: latest(emaSeries(completed, 20)),
    ema60: latest(emaSeries(completed, 60)),
    rsi14: rsi(completed.map((candle) => candle.close)),
    atr14: atr(completed),
    relativeActivity: averageActivity > 0 ? activity.at(-1)! / averageActivity : null,
  };
}

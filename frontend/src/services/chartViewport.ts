export type LogicalViewport = { from: number; to: number };
export type ChartViewportIdentity = { brokerServer: string | null; symbol: string | null; timeframe: string };

type ViewportStorage = Pick<Storage, "getItem" | "setItem">;

export const DEFAULT_VISIBLE_BARS = 108;
export const DEFAULT_RIGHT_OFFSET_BARS = 28;

export function chartViewportStorageKey({ brokerServer, symbol, timeframe }: ChartViewportIdentity): string {
  return ["pyontrading", "chart", "viewport", "v3", brokerServer ?? "UNAVAILABLE", symbol ?? "UNAVAILABLE", timeframe]
    .map(encodeURIComponent)
    .join(".");
}

export function legacyViewportStorageKey(timeframe: string): string {
  return `pyontrading.chart.viewport.v2.xauusd.${timeframe}`;
}

function parseViewport(value: string | null): LogicalViewport | null {
  try {
    const viewport = JSON.parse(value ?? "null") as LogicalViewport | null;
    return viewport && Number.isFinite(viewport.from) && Number.isFinite(viewport.to) && viewport.to > viewport.from ? viewport : null;
  } catch {
    return null;
  }
}

export function loadViewport(storage: ViewportStorage, identity: ChartViewportIdentity): LogicalViewport | null {
  const scopedKey = chartViewportStorageKey(identity);
  const scoped = parseViewport(storage.getItem(scopedKey));
  if (scoped) return scoped;
  if (identity.symbol !== "XAUUSD") return null;
  const legacy = parseViewport(storage.getItem(legacyViewportStorageKey(identity.timeframe)));
  if (legacy) storage.setItem(scopedKey, JSON.stringify(legacy));
  return legacy;
}

export function defaultViewportRange(candleCount: number): LogicalViewport {
  const to = Math.max(candleCount - 1, 0) + DEFAULT_RIGHT_OFFSET_BARS;
  return { from: Math.max(0, to - DEFAULT_VISIBLE_BARS), to };
}

export function visiblePriceRange<T extends { high: number; low: number; close: number }>(
  candles: T[], viewport: LogicalViewport,
): { from: number; to: number } | null {
  if (!candles.length) return null;
  const first = Math.max(0, Math.ceil(viewport.from));
  const last = Math.min(candles.length - 1, Math.floor(viewport.to));
  const visible = first <= last ? candles.slice(first, last + 1) : candles.slice(-DEFAULT_VISIBLE_BARS);
  const high = Math.max(...visible.map((candle) => candle.high));
  const low = Math.min(...visible.map((candle) => candle.low));
  const center = visible.at(-1)!.close;
  const halfRange = Math.max(high - center, center - low, center * 0.001) * 1.12;
  return { from: center - halfRange, to: center + halfRange };
}

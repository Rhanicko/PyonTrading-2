export type LogicalViewport = { from: number; to: number };

export const DEFAULT_VISIBLE_BARS = 108;
export const DEFAULT_RIGHT_OFFSET_BARS = 28;

export function defaultViewportRange(candleCount: number): LogicalViewport {
  const to = Math.max(candleCount - 1, 0) + DEFAULT_RIGHT_OFFSET_BARS;
  return { from: Math.max(0, to - DEFAULT_VISIBLE_BARS), to };
}

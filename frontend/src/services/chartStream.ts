import type { Candle } from "../types/api";

export function mergeFormingCandle(previous: Candle[], incoming: Candle): Candle[] {
  const last = previous.at(-1);
  if (!last) return [incoming];
  if (incoming.open_time_utc < last.open_time_utc) return previous;
  if (incoming.open_time_utc === last.open_time_utc) {
    if (last.completed && !incoming.completed) return previous;
    return [...previous.slice(0, -1), incoming];
  }
  return [...previous, incoming].slice(-2000);
}

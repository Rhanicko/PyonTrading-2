type QuoteFreshness = { data_status: string; observed_at_utc: string | null; tick_age_seconds: number | null };

export function isQuoteFresh(quote: QuoteFreshness | null, nowMs: number): boolean {
  if (!quote || quote.data_status !== "LIVE" || quote.tick_age_seconds === null || quote.tick_age_seconds > 5) return false;
  const observedMs = Date.parse(quote.observed_at_utc ?? "");
  const ageMs = nowMs - observedMs;
  return Number.isFinite(ageMs) && ageMs >= -2_000 && ageMs <= 6_000;
}

export function isWatchCurrent(expiresAtUtc: string | null, nowMs: number): boolean {
  const expiresMs = Date.parse(expiresAtUtc ?? "");
  return Number.isFinite(expiresMs) && nowMs < expiresMs;
}

export function isResearchFresh(observedAtUtc: string | null | undefined, nowMs: number): boolean {
  const ageMs = nowMs - Date.parse(observedAtUtc ?? "");
  return Number.isFinite(ageMs) && ageMs >= -2_000 && ageMs <= 15_000;
}

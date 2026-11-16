import type { SignalHistoryEntry } from "../types/api";

export function latestAutomaticSignal(entries: SignalHistoryEntry[], brokerServer: string, symbol: string): SignalHistoryEntry | null {
  return entries.find((entry) => entry.signal_kind === "AUTOMATIC" && entry.broker_server === brokerServer && entry.symbol === symbol) ?? null;
}

export function newSignalAlert(entries: SignalHistoryEntry[], lastSeenId: string | null, brokerServer: string, symbol: string, nowMs: number, sourceReady: boolean): SignalHistoryEntry | null {
  const latest = latestAutomaticSignal(entries, brokerServer, symbol);
  if (!sourceReady || lastSeenId === null || !latest || latest.signal_id === lastSeenId) return null;
  const expiry = Date.parse(latest.expires_at_utc ?? "");
  const provided = Date.parse(latest.provided_at_utc);
  if (!Number.isFinite(expiry) || !Number.isFinite(provided) || nowMs >= expiry || provided > nowMs + 2_000) return null;
  return latest.data_status === "LIVE" && latest.signal_proof?.publication_state === "ELIGIBLE"
    && latest.reference_levels && latest.decision !== "NO_TRADE" ? latest : null;
}

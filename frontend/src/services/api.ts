import type { Analysis, Backtest, Candles, ConfigurableStrategyId, Connection, Events, LiveResearchWatch, LocalSettings, MarketAnalysis, Operations, Quote, Research, SettingsUpdate, SignalHistory, SignalJournal, SourceCapabilities, StrategyJournal, StrategySettings, ValidationSummary } from "../types/api";

async function responseError(response: Response): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: { message?: string; reason_codes?: string[] } | string } | null;
  if (typeof payload?.detail === "string") return new Error(payload.detail);
  if (payload?.detail?.message) return new Error(payload.detail.message);
  if (payload?.detail?.reason_codes?.length) return new Error(payload.detail.reason_codes.join(" / "));
  return new Error(`REQUEST_${response.status}`);
}

async function request<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store", headers: { Accept: "application/json", "Cache-Control": "no-cache" } });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

async function post<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: "POST", cache: "no-store", headers: { Accept: "application/json", "Cache-Control": "no-cache" } });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
  const response = await fetch(path, { method: "PUT", cache: "no-store", headers: { "Content-Type": "application/json", Accept: "application/json", "Cache-Control": "no-cache", ...extraHeaders }, body: JSON.stringify(body) });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

export const api = {
  connection: () => request<Connection>("/api/connection"),
  quote: () => request<Quote>("/api/quote"),
  settings: () => request<LocalSettings>("/api/settings"),
  updateSettings: (payload: SettingsUpdate) => put<LocalSettings>("/api/settings", payload),
  candles: (timeframe: string, limit = 300) => request<Candles>(`/api/candles?tf=${encodeURIComponent(timeframe)}&limit=${limit}`),
  analysis: () => request<Analysis>("/api/analysis"),
  events: (scope: "upcoming" | "today" = "upcoming") => request<Events>(`/api/events?scope=${scope}`),
  signals: () => request<SignalJournal>("/api/signals"),
  signalHistory: () => request<SignalHistory>("/api/signals/history"),
  strategyJournal: () => request<StrategyJournal>("/api/strategy-journal"),
  strategySettings: () => request<StrategySettings>("/api/research/strategies"),
  updateStrategySetting: (strategyId: ConfigurableStrategyId, enabled: boolean, operatorToken: string) => put<StrategySettings>(`/api/research/strategies/${encodeURIComponent(strategyId)}`, { enabled }, { "X-Pyon-Operator-Token": operatorToken }),
  research: () => request<Research>("/api/research"),
  liveResearchWatch: () => request<LiveResearchWatch>("/api/research/live-watch"),
  validation: () => request<ValidationSummary>("/api/research/validation"),
  operations: () => request<Operations>("/api/research/operations"),
  sourceCapabilities: () => request<SourceCapabilities>("/api/sources/capabilities"),
  analyzeResearch: () => post<MarketAnalysis>("/api/research/analyze"),
  runBacktest: () => post<Backtest>("/api/backtests/run"),
};


import type { Analysis, Backtest, Candles, ConfigurableStrategyId, Connection, Events, HfmAccountFinancials, HfmAccountStatus, HfmDemoStatus, LiveResearchWatch, LocalSettings, MarketAnalysis, Operations, Quote, Research, ResearchPipelineStatus, SettingsUpdate, SignalHistory, SignalJournal, SourceCapabilities, StrategyJournal, StrategySettings, ValidationSummary, WalkForwardValidation } from "../types/api";

async function responseError(response: Response): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: { message?: string; reason_codes?: string[] } | string } | null;
  if (typeof payload?.detail === "string") return new Error(payload.detail);
  if (payload?.detail?.message) return new Error(payload.detail.message);
  if (payload?.detail?.reason_codes?.length) return new Error(payload.detail.reason_codes.join(" / "));
  return new Error(`REQUEST_${response.status}`);
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(new Error("REQUEST_TIMEOUT")), 15_000);
  try {
    const response = await fetch(path, { signal: signal ? AbortSignal.any([signal, timeout.signal]) : timeout.signal, cache: "no-store", headers: { Accept: "application/json", "Cache-Control": "no-cache" } });
    if (!response.ok) throw await responseError(response);
    return await response.json() as T;
  } finally { clearTimeout(timer); }
}

async function requestWithOperatorToken<T>(path: string, operatorToken: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store", headers: { Accept: "application/json", "Cache-Control": "no-cache", "X-Pyon-Operator-Token": operatorToken } });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

async function post<T>(path: string): Promise<T> {
  const response = await fetch(path, { method: "POST", cache: "no-store", headers: { Accept: "application/json", "Cache-Control": "no-cache" } });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

async function postWithOperatorToken<T>(path: string, body: unknown, operatorToken: string): Promise<T> {
  const response = await fetch(path, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json", Accept: "application/json", "Cache-Control": "no-cache", "X-Pyon-Operator-Token": operatorToken }, body: JSON.stringify(body) });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
  const response = await fetch(path, { method: "PUT", cache: "no-store", headers: { "Content-Type": "application/json", Accept: "application/json", "Cache-Control": "no-cache", ...extraHeaders }, body: JSON.stringify(body) });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
}

export const api = {
  marketScan: (signal?: AbortSignal) => request<import("../types/api").MarketScan>("/api/market/scan", signal),
  connection: () => request<Connection>("/api/connection"),
  hfmAccountStatus: () => request<HfmAccountStatus>("/api/hfm/account/status"),
  hfmAccountFinancials: (operatorToken: string) => requestWithOperatorToken<HfmAccountFinancials>("/api/hfm/account/financials", operatorToken),
  hfmDemoStatus: () => request<HfmDemoStatus>("/api/hfm/demo/status"),
  quote: () => request<Quote>("/api/quote"),
  settings: () => request<LocalSettings>("/api/settings"),
  updateSettings: (payload: SettingsUpdate) => put<LocalSettings>("/api/settings", payload),
  candles: (timeframe: string, limit = 300, signal?: AbortSignal) => request<Candles>(`/api/candles?tf=${encodeURIComponent(timeframe)}&limit=${limit}`, signal),
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
  pipeline: () => request<ResearchPipelineStatus>("/api/research/pipeline"),
  setPipelineEnabled: (enabled: boolean, operatorToken: string) => postWithOperatorToken<ResearchPipelineStatus>("/api/research/pipeline/control", { enabled }, operatorToken),
  sourceCapabilities: () => request<SourceCapabilities>("/api/sources/capabilities"),
  analyzeResearch: () => post<MarketAnalysis>("/api/research/analyze"),
  runBacktest: () => post<Backtest>("/api/backtests/run"),
  validateArchive: () => post<WalkForwardValidation>("/api/backtests/validate"),
};


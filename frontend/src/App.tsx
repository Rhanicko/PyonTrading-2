import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ConnectionWizard } from "./components/ConnectionWizard";
import { LiveResearchWatch } from "./components/LiveResearchWatch";
import { MarketReviewModal } from "./components/MarketReviewModal";
import { PriceChart, type ChartOverlayKey, type ChartOverlays } from "./components/PriceChart";
import { SignalHistoryPanel } from "./components/SignalHistoryPanel";
import { SignalProofAuditPanel } from "./components/SignalProofAuditPanel";
import { WalkForwardPanel } from "./components/WalkForwardPanel";
import { MarketScannerPanel } from "./components/MarketScannerPanel";
import { api } from "./services/api";
import { mergeFormingCandle } from "./services/chartStream";
import { age, pht, price, utc } from "./services/format";
import { tradingSession } from "./services/tradingSession";
import { isQuoteFresh } from "./services/liveFreshness";
import { latestAutomaticSignal, newSignalAlert } from "./services/signalNotifications";
import type { Backtest, BarEvent, Candles, ConfigurableStrategyId, Connection, Events, HfmAccountFinancials, HfmAccountStatus, HfmDemoStatus, LiveEvent, LiveResearchWatch as LiveResearchWatchData, LocalSettings, MarketAnalysis, Operations, Quote, Research, ResearchPipelineStatus, SignalHistory, SignalHistoryEntry, SignalJournal, SourceCapabilities, SourceCapability, StrategyJournal, StrategySettings, ValidationSummary } from "./types/api";

const frames = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
const chartWindowLimits: Record<string, number> = { M1: 1441, M5: 289, M15: 97, M30: 49, H1: 25, H4: 7, D1: 2 };
const defaultChartOverlays: ChartOverlays = { trend: true, vwap: true, bands: false, activity: true };
const chartOverlayLabels: Record<ChartOverlayKey, string> = { trend: "EMA 20 / 60", vwap: "VWAP proxy", bands: "Bands 20,2", activity: "Tick activity" };
const LIVE_RESEARCH_REFRESH_MS = 5_000;
const HFM_CONNECTION_REFRESH_MS = 10_000;
const HFM_FUNDS_REFRESH_MS = 5_000;
const usdAccountAmount = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", currencyDisplay: "code" });
type WorkspaceView = "desk" | "research" | "automation" | "validation" | "history" | "settings";
type OptionalSnapshotModule = "calendar" | "journal" | "signalHistory" | "strategyJournal" | "strategySettings" | "research" | "validation" | "operations" | "settings";
const workspaceViews: { id: WorkspaceView; label: string }[] = [
  { id: "desk", label: "Market desk" },
  { id: "research", label: "Research network" },
  { id: "automation", label: "Automation" },
  { id: "validation", label: "Validation" },
  { id: "history", label: "History" },
  { id: "settings", label: "Sources & rules" },
];

function workspaceViewFromUrl(): WorkspaceView {
  const requested = new URLSearchParams(window.location.search).get("view");
  return workspaceViews.find((view) => view.id === requested)?.id ?? "desk";
}

function statusTone(status?: string) { return status === "LIVE" ? "good" : status === "DELAYED" ? "watch" : "danger"; }
function localEventTime(value: string | null) { return value ? new Intl.DateTimeFormat("en-PH", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Manila", hour12: true }).format(new Date(value)) : "Time unavailable"; }
function requestMessage(cause: unknown, fallback: string) { return cause instanceof Error ? cause.message : fallback; }
function connectionKey(value: Connection | null) { return value ? JSON.stringify([value.terminal_path, value.broker_server, value.configured_symbol, value.account_mode, value.terminal_connected]) : ""; }
function capabilitySourceDetail(capability: SourceCapability) {
  const provider = capability.provider.replaceAll("_", " ");
  return capability.state === "READY" && capability.source_category === "UNAVAILABLE"
    ? provider
    : `${provider} · ${capability.source_category.replaceAll("_", " ")}`;
}
function hfmDemoGuidance(status: HfmDemoStatus): string {
  if (status.ready) return "The active HFM demo matches the locally bound account. This is a safety check only; PyonTrading does not place orders.";
  if (status.account_mode === "LIVE") return "Sign in to an HFM MT5 demo account. Live accounts are blocked from this demo workflow.";
  if (status.reason_codes.includes("DEMO_ACCOUNT_BINDING_NOT_CONFIGURED")) return "Set PYON_HFM_DEMO_LOGIN and PYON_HFM_DEMO_SERVER locally, then restart PyonTrading.";
  if (status.reason_codes.includes("DEMO_ACCOUNT_BINDING_MISMATCH")) return "The active MT5 account does not match the bound HFM demo account.";
  if (status.data_status === "DISCONNECTED") return "Open the HFM MT5 terminal and sign in to the intended demo account.";
  if (status.reason_codes.includes("TERMINAL_OR_ACCOUNT_TRADING_DISABLED")) return "Demo safety binding needs MT5 trading permissions; research access does not.";
  return status.reason_codes.join(" / ") || "The HFM demo account could not be verified.";
}
export default function App() {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [candles, setCandles] = useState<Candles | null>(null);
  const [calendar, setCalendar] = useState<Events | null>(null);
  const [journal, setJournal] = useState<SignalJournal | null>(null);
  const [signalHistory, setSignalHistory] = useState<SignalHistory | null>(null);
  const [newSignal, setNewSignal] = useState<SignalHistoryEntry | null>(null);
  const [desktopPermission, setDesktopPermission] = useState<NotificationPermission | "unsupported">(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
  const [strategyJournal, setStrategyJournal] = useState<StrategyJournal | null>(null);
  const [strategySettings, setStrategySettings] = useState<StrategySettings | null>(null);
  const [operatorToken, setOperatorToken] = useState("");
  const [updatingStrategy, setUpdatingStrategy] = useState<ConfigurableStrategyId | null>(null);
  const [research, setResearch] = useState<Research | null>(null);
  const [liveWatch, setLiveWatch] = useState<LiveResearchWatchData | null>(null);
  const [validation, setValidation] = useState<ValidationSummary | null>(null);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<ResearchPipelineStatus | null>(null);
  const [pipelineStatusError, setPipelineStatusError] = useState<string | null>(null);
  const [automationError, setAutomationError] = useState<string | null>(null);
  const [updatingPipeline, setUpdatingPipeline] = useState(false);
  const [modalAnalysis, setModalAnalysis] = useState<MarketAnalysis | null>(null);
  const [marketReviewView, setMarketReviewView] = useState<"open" | "minimized" | "closed">("closed");
  const [analyzingMarket, setAnalyzingMarket] = useState(false);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [runningBacktest, setRunningBacktest] = useState(false);
  const [sourceCapabilities, setSourceCapabilities] = useState<SourceCapabilities | null>(null);
  const [checkingSources, setCheckingSources] = useState(false);
  const [hfmAccountStatus, setHfmAccountStatus] = useState<HfmAccountStatus | null>(null);
  const [hfmFunds, setHfmFunds] = useState<HfmAccountFinancials | null>(null);
  const [hfmFundsError, setHfmFundsError] = useState<string | null>(null);
  const [targetHfmMode, setTargetHfmMode] = useState<"DEMO" | "LIVE">("DEMO");
  const [hfmDemoStatus, setHfmDemoStatus] = useState<HfmDemoStatus | null>(null);
  const [checkingHfmDemo, setCheckingHfmDemo] = useState(false);
  const [hfmDemoError, setHfmDemoError] = useState<string | null>(null);
  const [localSettings, setLocalSettings] = useState<LocalSettings | null>(null);
  const [contextDraft, setContextDraft] = useState({ dxy_symbol: "", us10y_symbol: "", wti_symbol: "", volatility_symbol: "" });
  const [savingContext, setSavingContext] = useState(false);
  const [timeframe, setTimeframe] = useState("M5");
  const [chartOverlays, setChartOverlays] = useState<ChartOverlays>(defaultChartOverlays);
  const [activeView, setActiveView] = useState<WorkspaceView>(workspaceViewFromUrl);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [moduleErrors, setModuleErrors] = useState<Partial<Record<OptionalSnapshotModule, string>>>({});
  const [now, setNow] = useState(new Date());
  const latestSequence = useRef(0);
  const candleRequest = useRef(0);
  const candleFlight = useRef<{ frame: string; controller: AbortController } | null>(null);
  const snapshotRefreshInFlight = useRef(false);
  const snapshotRefreshPending = useRef(false);
  const snapshotRequest = useRef(0);
  const researchRefreshInFlight = useRef(false);
  const supportingRefreshInFlight = useRef(false);
  const researchRequest = useRef(0);
  const sourceGeneration = useRef(0);
  const currentConnection = useRef<Connection | null>(null);
  const streamConnected = useRef(false);
  const lastStreamQuoteAt = useRef(0);
  const historyRefreshInFlight = useRef(false);
  const signalCursors = useRef<Record<string, string | null>>({});
  const hfmCheckInFlight = useRef(false);
  const currentTimeframe = useRef(timeframe);
  const contextDraftLoaded = useRef(false);
  const refreshCandlesRef = useRef<() => Promise<void>>(async () => {});
  const refreshSnapshotRef = useRef<() => Promise<void>>(async () => {});
  const refreshResearchRef = useRef<(allowSourceRetry?: boolean) => Promise<void>>(async () => {});

  const acceptConnection = useCallback((next: Connection) => {
    const previous = currentConnection.current;
    if (previous && Date.parse(next.observed_at_utc) < Date.parse(previous.observed_at_utc)) return false;
    const changed = connectionKey(previous) !== connectionKey(next);
    if (changed) {
      sourceGeneration.current++;
      lastStreamQuoteAt.current = 0;
      candleRequest.current++;
      candleFlight.current?.controller.abort();
      candleFlight.current = null;
      setQuote(null); setCandles(null); setResearch(null); setLiveWatch(null);
      setBacktest(null); setSourceCapabilities(null); setModalAnalysis(null);
      setJournal(null); setStrategyJournal(null);
      setMarketReviewView("closed"); setNewSignal(null); setHfmFunds(null);
    }
    currentConnection.current = next;
    setConnection(next);
    return changed;
  }, []);

  const acceptQuote = useCallback((next: Quote) => {
    const symbol = currentConnection.current?.configured_symbol;
    if (next.symbol !== symbol && (next.symbol !== null || next.data_status === "LIVE")) return;
    setQuote((previous) => previous && Date.parse(previous.observed_at_utc) > Date.parse(next.observed_at_utc) ? previous : next);
  }, []);

  const refreshCandles = useCallback(async () => {
    if (!currentConnection.current) return;
    if (candleFlight.current?.frame === timeframe) return;
    candleFlight.current?.controller.abort();
    const controller = new AbortController();
    candleFlight.current = { frame: timeframe, controller };
    const requestId = ++candleRequest.current;
    const generation = sourceGeneration.current;
    try {
      const nextCandles = await api.candles(timeframe, chartWindowLimits[timeframe] ?? 300, controller.signal);
      if (requestId === candleRequest.current && generation === sourceGeneration.current && nextCandles.symbol === currentConnection.current?.configured_symbol && nextCandles.timeframe === currentTimeframe.current) {
        setCandles((previous) => previous && Date.parse(previous.observed_at_utc) > Date.parse(nextCandles.observed_at_utc) ? previous : nextCandles);
      }
    } catch (cause) { if (!controller.signal.aborted && requestId === candleRequest.current && generation === sourceGeneration.current) setError(requestMessage(cause, "REQUEST_FAILED")); }
    finally { if (candleFlight.current?.controller === controller) candleFlight.current = null; }
  }, [timeframe]);

  const refreshSupportingData = useCallback(async (generation: number) => {
    if (supportingRefreshInFlight.current) return;
    supportingRefreshInFlight.current = true;
    try {
      const [calendarResult, journalResult, strategyJournalResult, operationsResult] = await Promise.allSettled([
        api.events("today"), api.signals(), api.strategyJournal(), api.operations(),
      ]);
      if (generation !== sourceGeneration.current) return;
      const nextErrors: Partial<Record<OptionalSnapshotModule, string>> = {};
      if (calendarResult.status === "fulfilled") setCalendar(calendarResult.value); else nextErrors.calendar = requestMessage(calendarResult.reason, "CALENDAR_REFRESH_FAILED");
      if (journalResult.status === "fulfilled") setJournal(journalResult.value); else nextErrors.journal = requestMessage(journalResult.reason, "JOURNAL_REFRESH_FAILED");
      if (strategyJournalResult.status === "fulfilled") setStrategyJournal(strategyJournalResult.value); else nextErrors.strategyJournal = requestMessage(strategyJournalResult.reason, "STRATEGY_JOURNAL_REFRESH_FAILED");
      if (operationsResult.status === "fulfilled") setOperations(operationsResult.value); else nextErrors.operations = requestMessage(operationsResult.reason, "OPERATIONS_REFRESH_FAILED");
      setModuleErrors((current) => {
        const next = { ...current };
        for (const module of ["calendar", "journal", "strategyJournal", "operations"] as const) {
          if (nextErrors[module]) next[module] = nextErrors[module]; else delete next[module];
        }
        return next;
      });
    } finally { supportingRefreshInFlight.current = false; }
  }, []);

  const refreshResearch = useCallback(async (allowSourceRetry = true) => {
    if (researchRefreshInFlight.current) return;
    researchRefreshInFlight.current = true;
    const requestId = ++researchRequest.current;
    let generation = sourceGeneration.current;
    let sourceChangedDuringRead = false;
    try {
      const connectionSnapshot = await api.connection();
      if (generation !== sourceGeneration.current) { sourceChangedDuringRead = true; return; }
      const changed = acceptConnection(connectionSnapshot);
      generation = sourceGeneration.current;
      void refreshSupportingData(generation);
      if (changed || !streamConnected.current || Date.now() - lastStreamQuoteAt.current > 6_000) {
        void refreshCandlesRef.current();
        const nextQuote = await api.quote();
        if (generation !== sourceGeneration.current) { sourceChangedDuringRead = true; return; }
        acceptQuote(nextQuote);
      }
      const currentResearch = await api.research();
      if (generation !== sourceGeneration.current) { sourceChangedDuringRead = true; return; }
      if (requestId !== researchRequest.current) return;
      // Verify the broker again: an MT5 session may change while its windows are read.
      const verifiedConnection = await api.connection();
      if (generation !== sourceGeneration.current) { sourceChangedDuringRead = true; return; }
      if (connectionKey(verifiedConnection) !== connectionKey(connectionSnapshot)) {
        acceptConnection(verifiedConnection);
        sourceChangedDuringRead = true;
        throw new Error("SOURCE_CHANGED_DURING_RESEARCH");
      }
      if (currentResearch.symbol !== verifiedConnection.configured_symbol || (currentResearch.live_research_watch && currentResearch.live_research_watch.symbol !== currentResearch.symbol)) {
        throw new Error("RESEARCH_SOURCE_MISMATCH");
      }
      setResearch(currentResearch);
      setLiveWatch(currentResearch.live_research_watch);
      setModuleErrors((current) => { const { research: _resolved, ...remaining } = current; return remaining; });
    } catch (cause) {
      if (generation === sourceGeneration.current || requestMessage(cause, "") === "SOURCE_CHANGED_DURING_RESEARCH") {
        setModuleErrors((current) => ({ ...current, research: requestMessage(cause, "RESEARCH_REFRESH_FAILED") }));
      }
    } finally {
      researchRefreshInFlight.current = false;
      // Follow a changed source immediately, but never spin on a flapping terminal.
      if (sourceChangedDuringRead && allowSourceRetry) void refreshResearchRef.current(false);
    }
  }, [acceptConnection, acceptQuote, refreshSupportingData]);

  const refreshSnapshot = useCallback(async () => {
    if (snapshotRefreshInFlight.current) { snapshotRefreshPending.current = true; return; }
    snapshotRefreshInFlight.current = true;
    const requestId = ++snapshotRequest.current;
    const requestedFrame = currentTimeframe.current;
    let generation = sourceGeneration.current;
    try {
      const connectionSnapshot = await api.connection();
      if (generation !== sourceGeneration.current) return;
      acceptConnection(connectionSnapshot);
      generation = sourceGeneration.current;
      void refreshSupportingData(generation);
      void refreshResearchRef.current();
      const optionalSnapshot = Promise.allSettled([
        api.signalHistory(), api.strategySettings(), api.validation(), api.settings(),
      ]);
      void optionalSnapshot.then((results) => {
        if (requestId !== snapshotRequest.current || generation !== sourceGeneration.current) return;
        const [signalHistoryResult, strategySettingsResult, validationResult, settingsResult] = results;
        const nextErrors: Partial<Record<OptionalSnapshotModule, string>> = {};
        if (signalHistoryResult.status === "fulfilled") setSignalHistory(signalHistoryResult.value); else nextErrors.signalHistory = requestMessage(signalHistoryResult.reason, "SIGNAL_HISTORY_REFRESH_FAILED");
        if (strategySettingsResult.status === "fulfilled") setStrategySettings(strategySettingsResult.value); else nextErrors.strategySettings = requestMessage(strategySettingsResult.reason, "STRATEGY_SETTINGS_REFRESH_FAILED");
        if (validationResult.status === "fulfilled") setValidation(validationResult.value); else nextErrors.validation = requestMessage(validationResult.reason, "VALIDATION_REFRESH_FAILED");
        if (settingsResult.status === "fulfilled") {
          setLocalSettings(settingsResult.value);
          if (!contextDraftLoaded.current) {
            setContextDraft({ dxy_symbol: settingsResult.value.dxy_symbol ?? "", us10y_symbol: settingsResult.value.us10y_symbol ?? "", wti_symbol: settingsResult.value.wti_symbol ?? "", volatility_symbol: settingsResult.value.volatility_symbol ?? "" });
            contextDraftLoaded.current = true;
          }
        } else nextErrors.settings = requestMessage(settingsResult.reason, "SETTINGS_REFRESH_FAILED");
        setModuleErrors((current) => {
          const next = { ...current };
          for (const module of ["signalHistory", "strategySettings", "validation", "settings"] as const) {
            if (nextErrors[module]) next[module] = nextErrors[module]; else delete next[module];
          }
          return next;
        });
      });
      const [currentQuote, currentCandles] = await Promise.all([api.quote(), api.candles(requestedFrame, chartWindowLimits[requestedFrame] ?? 300)]);
      if (requestId !== snapshotRequest.current || generation !== sourceGeneration.current) return;
      acceptQuote(currentQuote);
      if (currentCandles.timeframe === currentTimeframe.current && currentCandles.symbol === currentConnection.current?.configured_symbol) {
        setCandles((previous) => previous && Date.parse(previous.observed_at_utc) > Date.parse(currentCandles.observed_at_utc) ? previous : currentCandles);
      }
      setError(null);
    } catch (cause) { if (requestId === snapshotRequest.current) setError(requestMessage(cause, "REQUEST_FAILED")); }
    finally {
      snapshotRefreshInFlight.current = false; setLoading(false);
      if (snapshotRefreshPending.current) {
        snapshotRefreshPending.current = false;
        void refreshSnapshotRef.current();
      }
    }
  }, [acceptConnection, acceptQuote, refreshSupportingData]);

  useEffect(() => { currentTimeframe.current = timeframe; refreshCandlesRef.current = refreshCandles; refreshSnapshotRef.current = refreshSnapshot; refreshResearchRef.current = refreshResearch; }, [refreshCandles, refreshResearch, refreshSnapshot, timeframe]);
  useEffect(() => { void refreshSnapshot(); }, [refreshSnapshot]);
  useEffect(() => {
    setCandles((previous) => previous?.timeframe === timeframe ? previous : null);
    void refreshCandles();
  }, [refreshCandles, timeframe]);
  useEffect(() => { const id = window.setInterval(() => setNow(new Date()), 1_000); return () => window.clearInterval(id); }, []);
  useEffect(() => {
    const restoreView = () => setActiveView(workspaceViewFromUrl());
    window.addEventListener("popstate", restoreView);
    return () => window.removeEventListener("popstate", restoreView);
  }, []);
  const navigateView = (view: WorkspaceView) => {
    if (view === activeView) return;
    const url = new URL(window.location.href);
    if (view === "desk") url.searchParams.delete("view");
    else url.searchParams.set("view", view);
    window.history.pushState(null, "", url);
    setActiveView(view);
  };
  useEffect(() => {
    if (marketReviewView !== "open") return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMarketReviewView("closed");
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [marketReviewView]);
  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let retryDelay = 1_000;
    let stopped = false;
    const connect = () => {
      const activeSocket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/live`);
      socket = activeSocket;
      activeSocket.onopen = () => {
        if (stopped || activeSocket !== socket) return;
        streamConnected.current = true;
        latestSequence.current = 0; retryDelay = 1_000;
        activeSocket.send("snapshot-ready");
        void refreshSnapshotRef.current();
      };
      activeSocket.onmessage = (event) => {
        if (stopped || activeSocket !== socket) return;
        let update: LiveEvent;
        try { update = JSON.parse(event.data) as LiveEvent; } catch { return; }
        if (!update?.payload) return;
        if (!Number.isInteger(update.sequence) || update.sequence <= latestSequence.current) return;
        latestSequence.current = update.sequence;
        if (update.type === "quote") {
          const incoming = update.payload as Quote;
          if (incoming.symbol !== currentConnection.current?.configured_symbol) return;
          if (isQuoteFresh(incoming, Date.now())) lastStreamQuoteAt.current = Date.now();
          acceptQuote(incoming);
          if (currentTimeframe.current !== "M5") void refreshCandlesRef.current();
        }
        if (update.type === "bar_update" && currentTimeframe.current === "M5") {
          const bar = update.payload as BarEvent;
          if (bar.symbol !== currentConnection.current?.configured_symbol || bar.timeframe !== "M5" || !bar.candle) return;
          setCandles((current) => current?.timeframe === "M5" && current.symbol === bar.symbol && Date.parse(current.observed_at_utc) <= Date.parse(update.observed_at_utc) ? { ...current, data_status: bar.data_status, reason_codes: bar.reason_codes, observed_at_utc: update.observed_at_utc, candles: mergeFormingCandle(current.candles, bar.candle) } : current);
        }
        if (update.type === "bar_closed" && (update.payload as BarEvent).symbol === currentConnection.current?.configured_symbol) {
          void refreshCandlesRef.current();
          void refreshResearchRef.current();
        }
        if (update.type === "provider_status" || (update.type === "heartbeat" && ["SOURCE_ERROR", "DISCONNECTED", "STALE", "MARKET_CLOSED"].includes(update.payload.data_status))) {
          const status = update.payload.data_status;
          setQuote((previous) => previous ? { ...previous, data_status: status, reason_codes: update.payload.reason_codes } : previous);
          void refreshSnapshotRef.current();
        }
      };
      activeSocket.onclose = () => {
        if (stopped || activeSocket !== socket) return;
        streamConnected.current = false;
        setQuote((previous) => previous?.data_status === "LIVE" ? { ...previous, data_status: "STALE", reason_codes: ["LIVE_STREAM_DISCONNECTED"] } : previous);
        setModuleErrors((current) => ({ ...current, research: "LIVE_STREAM_DISCONNECTED; reconnecting with AJAX fallback" }));
        retryTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 15_000);
      };
    };
    connect();
    return () => { stopped = true; streamConnected.current = false; if (retryTimer) window.clearTimeout(retryTimer); socket?.close(); };
  }, [acceptQuote]);
  useEffect(() => { const id = window.setInterval(() => void refreshResearchRef.current(), LIVE_RESEARCH_REFRESH_MS); return () => window.clearInterval(id); }, []);
  useEffect(() => {
    const id = window.setInterval(async () => {
      if (historyRefreshInFlight.current) return;
      historyRefreshInFlight.current = true;
      try {
        setSignalHistory(await api.signalHistory());
        setModuleErrors((current) => { const { signalHistory: _resolvedHistoryError, ...remaining } = current; return remaining; });
      } catch (cause) {
        setModuleErrors((current) => ({ ...current, signalHistory: requestMessage(cause, "SIGNAL_HISTORY_REFRESH_FAILED") }));
      } finally {
        historyRefreshInFlight.current = false;
      }
    }, 5_000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => {
    const broker = connection?.broker_server;
    const symbol = connection?.configured_symbol;
    if (!signalHistory || !broker || !symbol) return;
    const latest = latestAutomaticSignal(signalHistory.entries, broker, symbol);
    const key = `pyontrading.signal.cursor.v1.${encodeURIComponent(broker)}.${encodeURIComponent(symbol)}`;
    if (!(key in signalCursors.current)) {
      let stored: string | null = null;
      try { stored = window.localStorage.getItem(key); } catch { /* Keep an in-tab cursor. */ }
      signalCursors.current[key] = stored ?? latest?.signal_id ?? "";
      if (stored === null) {
        try { window.localStorage.setItem(key, signalCursors.current[key]!); } catch { /* Keep an in-tab cursor. */ }
      }
    }
    if (!latest) return;
    const alertTime = Date.now();
    const sourceReady = connection?.terminal_connected === true && connection.data_status === "LIVE" && isQuoteFresh(quote, alertTime);
    const alert = newSignalAlert(signalHistory.entries, signalCursors.current[key], broker, symbol, alertTime, sourceReady);
    if (latest.signal_id !== signalCursors.current[key]) {
      signalCursors.current[key] = latest.signal_id;
      try { window.localStorage.setItem(key, latest.signal_id); } catch { /* Alerts still work in this tab. */ }
    }
    if (alert) {
      setNewSignal(alert);
      if (typeof Notification !== "undefined" && Notification.permission === "granted") {
        const levels = alert.reference_levels!;
        try { new Notification(`PyonTrading ${alert.decision.replace("_", " ")}`, { body: `${alert.symbol} · Entry ${levels.entry.toFixed(2)} · Stop ${levels.stop_loss.toFixed(2)} · TP1 ${levels.take_profit_1.toFixed(2)} · TP2 ${levels.take_profit_2.toFixed(2)}. Unvalidated research only.`, tag: alert.signal_id }); }
        catch { /* The in-app alert remains available. */ }
      }
    }
  }, [signalHistory, connection, quote]);
  const enableDesktopAlerts = async () => {
    if (typeof Notification === "undefined" || Notification.permission !== "default") return;
    try { setDesktopPermission(await Notification.requestPermission()); }
    catch { setDesktopPermission("denied"); }
  };

  const saveSymbol = async (symbol: string) => {
    try {
      const saved = await api.updateSettings({ symbol, timezone: "Asia/Manila", max_risk_percent: localSettings?.max_risk_percent ?? 0.5 });
      setLocalSettings(saved);
      setError(null);
      await refreshSnapshot();
    } catch { setError("SYMBOL_SAVE_FAILED"); }
  };
  const analyzeMarket = async () => {
    setAnalyzingMarket(true);
    try {
      const result = await api.analyzeResearch();
      setModalAnalysis(result);
      setMarketReviewView("open");
      void api.signalHistory().then(setSignalHistory).catch(() => undefined);
      setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "MARKET_ANALYSIS_FAILED"); }
    finally { setAnalyzingMarket(false); }
  };
  const runBacktest = async () => {
    setRunningBacktest(true);
    try {
      const result = await api.runBacktest();
      setBacktest(result);
      setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "BACKTEST_FAILED"); }
    finally { setRunningBacktest(false); }
  };
  const checkSources = async () => {
    setCheckingSources(true);
    try {
      setSourceCapabilities(await api.sourceCapabilities());
      setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "SOURCE_CAPABILITY_CHECK_FAILED"); }
    finally { setCheckingSources(false); }
  };
  const checkHfmDemo = useCallback(async () => {
    if (hfmCheckInFlight.current) return;
    hfmCheckInFlight.current = true;
    setCheckingHfmDemo(true);
    try {
      const accountStatus = await api.hfmAccountStatus();
      setHfmAccountStatus(accountStatus);
      setHfmDemoStatus(null);
      setHfmDemoError(null);
      if (accountStatus.connected && accountStatus.account_mode === "DEMO") {
        try { setHfmDemoStatus(await api.hfmDemoStatus()); }
        catch (cause) { setHfmDemoError(`Optional demo binding check failed: ${requestMessage(cause, "HFM_DEMO_CHECK_FAILED")}`); }
      }
    } catch (cause) {
      setHfmAccountStatus(null);
      setHfmDemoStatus(null);
      setHfmDemoError(requestMessage(cause, "HFM_CONNECTION_CHECK_FAILED"));
    } finally { hfmCheckInFlight.current = false; setCheckingHfmDemo(false); }
  }, []);
  useEffect(() => {
    if (activeView !== "settings" && activeView !== "automation") return;
    void checkHfmDemo();
    const id = window.setInterval(() => void checkHfmDemo(), HFM_CONNECTION_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [activeView, checkHfmDemo]);
  useEffect(() => {
    if (activeView !== "automation") return;
    const refresh = () => void api.pipeline().then((status) => { setPipelineStatus(status); setPipelineStatusError(null); }).catch((cause) => setPipelineStatusError(requestMessage(cause, "PIPELINE_STATUS_FAILED")));
    refresh();
    const id = window.setInterval(refresh, 5_000);
    return () => window.clearInterval(id);
  }, [activeView]);
  useEffect(() => {
    setHfmFunds(null);
    setHfmFundsError(null);
    if (activeView !== "automation" || !operatorToken.trim()) return;
    let active = true;
    let inFlight = false;
    const refresh = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const financials = await api.hfmAccountFinancials(operatorToken);
        if (active) { setHfmFunds(financials); setHfmFundsError(null); }
      } catch (cause) {
        if (active) { setHfmFunds(null); setHfmFundsError(requestMessage(cause, "HFM_FINANCIALS_UNAVAILABLE")); }
      } finally { inFlight = false; }
    };
    const initial = window.setTimeout(() => void refresh(), 300);
    const interval = window.setInterval(() => void refresh(), HFM_FUNDS_REFRESH_MS);
    return () => { active = false; window.clearTimeout(initial); window.clearInterval(interval); };
  }, [activeView, operatorToken]);
  const controlPipeline = async (enabled: boolean) => {
    if (!operatorToken.trim()) { setAutomationError("OPERATOR_TOKEN_REQUIRED"); return; }
    setUpdatingPipeline(true);
    try {
      setPipelineStatus(await api.setPipelineEnabled(enabled, operatorToken));
      setAutomationError(null);
    } catch (cause) { setAutomationError(requestMessage(cause, "PIPELINE_CONTROL_FAILED")); }
    finally { setUpdatingPipeline(false); }
  };
  const toggleChartOverlay = (overlay: ChartOverlayKey) => setChartOverlays((current) => ({ ...current, [overlay]: !current[overlay] }));
  const saveCrossMarketContext = async () => {
    setSavingContext(true);
    try {
      const saved = await api.updateSettings({
        timezone: "Asia/Manila",
        max_risk_percent: localSettings?.max_risk_percent ?? 0.5,
        dxy_symbol: contextDraft.dxy_symbol.trim() || null,
        us10y_symbol: contextDraft.us10y_symbol.trim() || null,
        wti_symbol: contextDraft.wti_symbol.trim() || null,
        volatility_symbol: contextDraft.volatility_symbol.trim() || null,
      });
      setLocalSettings(saved);
      setContextDraft({ dxy_symbol: saved.dxy_symbol ?? "", us10y_symbol: saved.us10y_symbol ?? "", wti_symbol: saved.wti_symbol ?? "", volatility_symbol: saved.volatility_symbol ?? "" });
      contextDraftLoaded.current = true;
      await Promise.all([refreshSnapshot(), checkSources()]);
      setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "CONTEXT_SYMBOL_SAVE_FAILED"); }
    finally { setSavingContext(false); }
  };
  const toggleStrategy = async (strategyId: ConfigurableStrategyId, enabled: boolean) => {
    if (!operatorToken.trim()) { setError("OPERATOR_TOKEN_REQUIRED"); return; }
    setUpdatingStrategy(strategyId);
    try {
      setStrategySettings(await api.updateStrategySetting(strategyId, enabled, operatorToken));
      setError(null);
      await refreshSnapshot();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "STRATEGY_SETTING_SAVE_FAILED"); }
    finally { setUpdatingStrategy(null); }
  };
  const forming = candles?.candles.find((candle) => !candle.completed);
  const completedCandleCount = candles?.candles.filter((candle) => candle.completed).length ?? 0;
  const formingCandleCount = candles?.candles.filter((candle) => !candle.completed).length ?? 0;
  const chartContext = candles?.candles.length
    ? `${timeframe} broker-candle data · ${completedCandleCount} completed${formingCandleCount ? ` · ${formingCandleCount} forming` : ""}`
    : `${timeframe} broker-candle data · ${candles?.data_status ?? "AWAITING"}`;
  const latestEvaluation = journal?.evaluations[0];
  const latestStrategyEvent = strategyJournal?.events[0];
  const latestObservationIsDataOnly = latestEvaluation?.evaluation_type === "DATA_OBSERVATION";
  const latestObservationTitle = latestObservationIsDataOnly ? "M5 CANDLE RECORDED" : latestEvaluation?.market_state ?? "Awaiting M5 close";
  const latestObservationCode = latestObservationIsDataOnly
    ? "DATA OBSERVATION ONLY / NO ORDER EXECUTION"
    : latestEvaluation?.reason_codes[0] ?? journal?.reason_codes[0] ?? "AWAITING_COMPLETED_CANDLE";
  const todayEvents = calendar?.events ?? [];
  const bots = research?.bots ?? [];
  const botCoordination = useMemo(() => {
    const liveBots = bots.filter((bot) => bot.data_status === "LIVE" && bot.state !== "BLOCKED").length;
    const blockedBots = bots.filter((bot) => bot.state === "BLOCKED").length;
    const notConfiguredBots = bots.filter((bot) => bot.state !== "BLOCKED" && bot.data_status === "NOT_CONFIGURED").length;
    const degradedBots = bots.filter((bot) => bot.state !== "BLOCKED" && bot.data_status !== "LIVE" && bot.data_status !== "NOT_CONFIGURED").length;
    const ensemble = research?.strategy_ensemble;
    return {
      totalBots: bots.length,
      liveBots,
      blockedBots,
      notConfiguredBots,
      degradedBots,
      agreementCount: ensemble?.agreement_count ?? null,
      requiredAgreementCount: ensemble?.required_agreement_count ?? null,
      ensembleDecision: ensemble?.decision ?? null,
    };
  }, [bots, research]);
  const professional = research?.professional_analysis;
  const m5Archive = sourceCapabilities?.archives.find((archive) => archive.timeframe === "M5");
  const displayTime = useMemo(() => new Intl.DateTimeFormat("en-PH", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Manila", hour12: true }).format(now), [now]);
  const setupRequired = connection && (!connection.terminal_connected || !connection.configured_symbol);
  const currentSession = tradingSession(now);
  const activeOverlayCount = Object.values(chartOverlays).filter(Boolean).length;
  const quoteFresh = isQuoteFresh(quote, now.getTime());
  const quoteStatus = quote?.data_status === "LIVE" && !quoteFresh ? "STALE" : quote?.data_status ?? connection?.data_status ?? "CONNECTING";
  const quoteAgeSeconds = quote?.observed_at_utc ? (now.getTime() - Date.parse(quote.observed_at_utc)) / 1_000 : null;
  const researchCoverage = pipelineStatus?.coverage;
  const researchCoverageLabel = !researchCoverage ? "Research unverified"
    : researchCoverage.state === "SOURCE_UNAVAILABLE" && quoteStatus === "MARKET_CLOSED" ? "Awaiting market"
    : researchCoverage.state === "CURRENT" || researchCoverage.state === "CURRENT_WITH_GAPS" ? "Research current"
      : researchCoverage.state === "NO_ARCHIVE" || researchCoverage.state === "SOURCE_IDENTITY_UNAVAILABLE" || researchCoverage.state === "NO_RESEARCH_HISTORY" ? "Research unavailable" : "Research stale";
  const fundsFresh = hfmFunds?.data_status === "LIVE" && hfmFunds.currency === "USD"
    && hfmFunds.balance !== null && hfmFunds.equity !== null
    && Math.abs(now.getTime() - Date.parse(hfmFunds.observed_at_utc)) <= 15_000;

  return <main className={`workstation${activeView === "desk" && !setupRequired && !loading && !error ? " market-desk-page" : ""}`}>
    <a className="skip-link" href="#market-desk">Skip to market desk</a>
    <header className="topbar">
      <div className="brand"><div className="brand-mark">P2</div><div><strong>PyonTrading</strong><span>READ-ONLY MARKET WORKSTATION</span></div></div>
      <div className="instrument"><span>INSTRUMENT</span><strong>{connection?.configured_symbol ?? "SYMBOL NOT SELECTED"}</strong><small>{connection?.broker_server ?? "MT5 connection required"}</small></div>
      <div className="quotes"><div><span>BID</span><strong>{price(quoteFresh ? quote?.bid ?? null : null)}</strong></div><div><span>ASK</span><strong>{price(quoteFresh ? quote?.ask ?? null : null)}</strong></div><div><span>SPREAD</span><strong>{quoteFresh && quote?.spread_points != null ? `${quote.spread_points.toFixed(1)} pt` : "—"}</strong></div></div>
      <div className="status-block" role="status"><span className={`status-dot ${statusTone(quoteStatus)}`} /><div><strong>{quoteStatus}</strong><small>Observed: {pht(quote?.observed_at_utc ?? null)} PHT · {age(quoteAgeSeconds !== null && Number.isFinite(quoteAgeSeconds) ? Math.max(0, quoteAgeSeconds) : null)}{quote?.timestamp_normalized ? ` · Broker clock +${(quote.broker_clock_offset_seconds ?? 0) / 3600}h normalized` : ""}</small></div></div>
      <div className="clock">
        <div className="session-clock" role="status" aria-label="Current trading session" title="Indicative FX sessions, calculated from city-local business hours and daylight saving. Not broker symbol availability or a holiday calendar."><span>{currentSession.overlap ? "SESSION OVERLAP" : "TRADING SESSION"}</span><strong>{currentSession.label}</strong></div>
        <div className="local-clock"><span>PHILIPPINES TIME</span><strong>{displayTime}</strong></div>
      </div>
    </header>

    {error && <div className="error-strip" role="alert">Unable to refresh broker data: {error}. No price has been substituted.</div>}
    {loading && <div className="loading-strip">Checking local MT5 terminal…</div>}
    {setupRequired && <ConnectionWizard connection={connection} onRetry={() => void refreshSnapshot()} onSave={saveSymbol} />}
    <nav className="desk-navigation" aria-label="Workstation sections">
      <div className="desk-navigation-links">
        {workspaceViews.map((view) => <button key={view.id} type="button" className={activeView === view.id ? "active" : ""} aria-current={activeView === view.id ? "page" : undefined} onClick={() => navigateView(view.id)}>{view.label}</button>)}
      </div>
      <span className="desk-boundary">Research only · no order execution</span>
    </nav>

    <div className={activeView === "desk" ? "market-layout" : undefined}>
    <section id="market-desk" className={`workspace-grid ${activeView === "research" ? "research-workspace" : "desk-workspace"}`} hidden={activeView !== "desk" && activeView !== "research"}>
      <section className="chart-panel panel" hidden={activeView !== "desk"}>
        <div className="panel-heading"><div className="chart-title"><h1>{connection?.configured_symbol ?? "XAUUSD"} <small>· {timeframe}</small></h1><div className="chart-context-line"><strong>{chartContext}</strong></div></div><div className="source-chip">MT5 · {(quoteStatus === "LIVE" ? candles?.data_status ?? "AWAITING" : quoteStatus).replaceAll("_", " ")}</div></div>
        <div className="chart-toolbar">
          <nav className="timeframes" aria-label="Chart timeframe">{frames.map((frame) => <button key={frame} className={frame === timeframe ? "selected" : ""} onClick={() => setTimeframe(frame)}>{frame}</button>)}</nav>
          <details className="chart-options"><summary>Indicators <span>{activeOverlayCount} active</span></summary><div className="chart-tools" aria-label="Chart overlay controls"><div>{(Object.keys(chartOverlayLabels) as ChartOverlayKey[]).map((overlay) => <button key={overlay} type="button" aria-pressed={chartOverlays[overlay]} onClick={() => toggleChartOverlay(overlay)}>{chartOverlayLabels[overlay]}</button>)}</div><small>Descriptive research context from completed broker candles.</small></div></details>
        </div>
        {candles?.candles.length ? <><PriceChart candles={candles.candles} timeframe={timeframe} overlays={chartOverlays} brokerServer={connection?.broker_server ?? null} symbol={candles.symbol ?? connection?.configured_symbol ?? null} /><div className="chart-footer"><span>Completed candles: {completedCandleCount}</span><span className="forming">{forming ? `${quoteStatus === "LIVE" ? `FORMING ${timeframe}` : `LAST ${timeframe} BAR`} · ${utc(forming.open_time_utc)} UTC` : `NO FORMING ${timeframe} BAR`}</span><a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">Charting by TradingView</a></div></> : <div className="chart-empty"><div className="empty-icon">×</div><h2>No broker candles available</h2><p>{candles?.reason_codes[0] ?? "Connect MT5 and select your exact broker symbol to request real candles."}</p></div>}
      </section>

      <aside className={`research-panel panel ${activeView === "research" ? "research-view" : "desk-view"}`}>
        <LiveResearchWatch watch={liveWatch} quote={quote} quoteFresh={quoteFresh} nowMs={now.getTime()} moduleError={moduleErrors.research} coordination={botCoordination} onSaveReview={() => void analyzeMarket()} savingReview={analyzingMarket} />
        {activeView === "desk" && <button type="button" className="research-link" onClick={() => navigateView("research")}>View research network <span>{bots.length} bot reports</span></button>}
        {activeView === "research" && <section className="bot-network" aria-label="Connected research bots">
          <div className="network-heading"><div><span className="eyebrow">CONNECTED RESEARCH BOTS</span><h2>{bots.length ? `${bots.length} source-backed observers` : "Waiting for research inputs"}</h2></div><strong>M5 / M15 / H1 / H4</strong></div>
          {bots.length ? bots.map((bot, index) => <details className={`bot-card ${bot.state.toLowerCase()}`} key={bot.bot_id}><summary><span className="bot-index">{String(index + 1).padStart(2, "0")}</span><span><strong>{bot.label}</strong><small>{bot.state.replaceAll("_", " ")} · {bot.data_status}</small></span><span className="bot-open-label">Details</span></summary><p>{bot.summary}</p>{bot.skills.length > 0 && <div className="bot-skills" aria-label={`${bot.label} skills`}>{bot.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>}{bot.facts.length > 0 && <ul className="bot-facts">{bot.facts.slice(0, 4).map((fact) => <li key={fact}>{fact}</li>)}</ul>}</details>) : <div className="bot-empty">Waiting for source-backed research inputs.</div>}
        </section>}
      </aside>
    </section>

    {activeView !== "desk" && activeView !== "research" && <header className="view-heading"><span className="eyebrow">WORKSTATION AREA</span><h2>{workspaceViews.find((view) => view.id === activeView)?.label}</h2><p>{activeView === "automation" ? "Control the background research worker; broker order execution remains unavailable." : activeView === "validation" ? "Chronological research, paper evidence, and source-labelled limitations." : activeView === "history" ? "Automatic research signals and on-demand reviews, preserved with their decision-time evidence." : "Local source, context, and rule configuration."}</p></header>}
    {activeView === "research" && <MarketScannerPanel key={connectionKey(connection)} />}
    <section className={`lower-grid ${activeView}-grid`} hidden={activeView === "research"}>
      <article className="panel lower-card automation-controller-card" aria-label="Research automation controller" hidden={activeView !== "automation"}>
        <span className="eyebrow">BACKGROUND RESEARCH</span>
        <h2>{pipelineStatus?.state === "RUNNING" ? "Research running" : pipelineStatus?.state === "PAUSED" ? "Research paused" : pipelineStatus?.state === "PAUSING" ? "Pausing research" : pipelineStatus?.state === "STOPPED" ? "Worker stopped" : "Checking worker"}</h2>
        <p>Completed-candle collection, research jobs, and outcome labels run in the background. Pausing takes effect after any active cycle finishes.</p>
        <dl className="automation-facts"><div><dt>Symbol</dt><dd>{pipelineStatus?.symbol ?? "Not selected"}</dd></div><div><dt>Last cycle</dt><dd>{pipelineStatus?.last_cycle_at_utc ? `${pht(pipelineStatus.last_cycle_at_utc)} PHT` : "Not yet run"}</dd></div><div><dt>Worker error</dt><dd>{pipelineStatus?.last_error ?? "None reported"}</dd></div></dl>
        <section className="research-coverage" aria-label="Research coverage">
          <div className="research-coverage-heading"><strong>Research health</strong><div className="research-coverage-states"><span>{quoteStatus === "LIVE" ? "Quote live" : `Quote ${quoteStatus.toLowerCase().replaceAll("_", " ")}`}</span>{researchCoverage?.worker_health && <span className={researchCoverage.worker_health === "RUNNING" ? "" : "attention"}>Worker {researchCoverage.worker_health.toLowerCase()}</span>}</div></div>
          <div className="research-coverage-summary"><strong>{researchCoverageLabel}</strong><span>{researchCoverage?.publication_state === "BLOCKED" ? "Publication blocked" : researchCoverage ? "Signal proof still required" : "Publication status unavailable"}</span></div>
          {researchCoverage ? <><dl className="automation-facts"><div><dt>Last archived M5 open</dt><dd>{researchCoverage.latest_completed_m5_open_utc ? `${pht(researchCoverage.latest_completed_m5_open_utc)} PHT` : "Unavailable"}</dd></div><div><dt>Last decision M5 open</dt><dd>{researchCoverage.latest_decision_m5_open_utc ? `${pht(researchCoverage.latest_decision_m5_open_utc)} PHT` : "None"}</dd></div><div><dt>Historical coverage</dt><dd>{researchCoverage.unprocessed_archived_bars} archived bars without decisions</dd></div></dl><small>Historical run identity is symbol-scoped; broker identity was not retained in legacy decisions. Backfilled bars are not live signals.</small></> : <p>Coverage details are not available from this worker version.</p>}
        </section>
        <label className="operator-token-field">Local operator token<input type="password" value={operatorToken} onChange={(event) => setOperatorToken(event.target.value)} autoComplete="off" placeholder="Required to change worker state" /></label>
        <small>Set PYON_OPERATOR_TOKEN before starting the local app. The browser does not save this token.</small>
        <section className="account-funds" aria-label="HFM account funds" aria-live="polite">
          <div className="account-funds-heading"><strong>HFM account funds</strong><span>{fundsFresh ? `${hfmFunds.account_mode} · ••••${hfmFunds.account_id_suffix ?? ""}` : "USD balance unavailable"}</span></div>
          {fundsFresh ? <><dl className="automation-facts"><div><dt>Balance</dt><dd>{usdAccountAmount.format(hfmFunds.balance!)}</dd></div><div><dt>Equity</dt><dd>{usdAccountAmount.format(hfmFunds.equity!)}</dd></div></dl><small>MT5 account snapshot · observed {pht(hfmFunds.observed_at_utc)} PHT · refreshed every 5 seconds</small></>
            : <p>{!operatorToken.trim() ? "Enter operator token to view HFM USD balance." : hfmFundsError ?? hfmFunds?.reason_codes.join(" / ") ?? "Checking the active HFM MT5 account…"}</p>}
        </section>
        <button type="button" className="analyze-button" disabled={!pipelineStatus || updatingPipeline || pipelineStatus.state === "PAUSING" || pipelineStatus.state === "STOPPED"} onClick={() => void controlPipeline(!pipelineStatus?.enabled)}>{updatingPipeline ? "Updating…" : pipelineStatus?.state === "STOPPED" ? "Restart app to recover worker" : pipelineStatus?.enabled ? "Pause research" : "Resume research"}</button>
        {(pipelineStatusError || automationError) && <p className="module-error" role="alert">{automationError ?? pipelineStatusError}</p>}
      </article>
      <article className="panel lower-card automation-boundary-card" hidden={activeView !== "automation"}>
        <span className="eyebrow">BROKER ORDER AUTOMATION</span><h2>Unavailable</h2>
        <p>Broker order automation is unavailable in this version. This controller changes research collection only; it never arms MT5 trading.</p>
        <dl className="automation-facts"><div><dt>HFM demo</dt><dd>{hfmAccountStatus?.connected && hfmAccountStatus.account_mode === "DEMO" ? "Connected" : "Not verified"}</dd></div><div><dt>Calibration</dt><dd>{validation?.calibration_state?.replaceAll("_", " ") ?? "Checking"}</dd></div><div><dt>Costs</dt><dd>{validation?.cost_status?.replaceAll("_", " ") ?? "Checking"}</dd></div></dl>
        <small>Real-account execution remains locked. Research outcomes are not training or profit guarantees.</small>
      </article>
      <article className="panel lower-card today-events-card" hidden={activeView !== "desk"}><span className="eyebrow">TODAY'S USD CALENDAR</span><h2>{calendar?.data_status ?? "CHECKING"}</h2>{moduleErrors.calendar && <p className="module-error">Calendar refresh issue: {moduleErrors.calendar}</p>}{todayEvents.length ? <ul className="today-events-list">{todayEvents.map((event) => <li key={`${event.title}-${event.event_time_utc}`}><span className={`impact impact-${event.impact.toLowerCase()}`}>{event.impact}</span><div><strong>{event.title}</strong><small>{localEventTime(event.event_time_manila)} PHT</small></div></li>)}</ul> : <p>{calendar?.data_status === "LIVE" ? "No remaining USD events in today's public export. This is not a no-news guarantee." : "Today's USD calendar is unavailable; news risk is unverified."}</p>}<code>{calendar?.reason_codes[0] ?? "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT"}</code></article>
      <article className="panel lower-card journal-card" hidden={activeView !== "desk"}><span className="eyebrow">LATEST OBSERVATION</span><h2>{latestObservationTitle}</h2><p>{latestEvaluation ? <>Completed M5 candle recorded {pht(latestEvaluation.candle_open_utc)} PHT. This is evidence, not a signal.</> : "Completed M5 observations are retained locally when the broker supplies them."}</p><code>{latestObservationCode}</code></article>
      <SignalProofAuditPanel summary={validation} hidden={activeView !== "validation"} />
      <article className="panel lower-card backtest-card" hidden={activeView !== "validation"}><span className="eyebrow">BACKTESTING LAB</span><div className="backtest-heading"><h2>Historical M5 research</h2><button type="button" className="analyze-button" onClick={() => void runBacktest()} disabled={runningBacktest}>{runningBacktest ? "Running…" : "Run backtest"}</button></div>{backtest ? <><p>{backtest.completed_candles} completed broker candles examined. {backtest.limitation}</p><ul className="backtest-results">{backtest.results.map((result) => <li key={result.strategy_id}><strong>{result.strategy_id.replaceAll("_", " ")}</strong><span>{result.completed_trials} trials · {result.observed_signals} observed</span></li>)}</ul><code>{backtest.reason_codes.join(" / ")}</code></> : <p>Runs completed-candle research only. Results remain unavailable when broker history or execution-cost inputs are incomplete.</p>}</article>
      <WalkForwardPanel hidden={activeView !== "validation"} />
      <article className="panel lower-card" hidden={activeView !== "validation"}><span className="eyebrow">VOLUME & ORDER FLOW</span><h2>{professional?.volume_source_category.replaceAll("_", " ") ?? "CHECKING"}</h2><p>{professional ? `VWAP: ${professional.volume_momentum.vwap_basis}. Profile: ${professional.volume_profile.state.replaceAll("_", " ")}. Genuine footprint/COMEX delta: ${professional.market_depth.source_category === "UNAVAILABLE" ? "unavailable" : "source retained"}.` : "Waiting for completed broker candles."}</p><code>{professional?.market_depth.reason_codes[0] ?? "SOURCE_CLASSIFICATION_PENDING"}</code></article>
      <article className="panel lower-card" hidden={activeView !== "validation"}><span className="eyebrow">STRATEGY JOURNAL</span><h2>{latestStrategyEvent?.state.replaceAll("_", " ") ?? "AWAITING M5 CLOSE"}</h2><p>{latestStrategyEvent ? `${latestStrategyEvent.strategy_id.replaceAll("_", " ")} · ${latestStrategyEvent.direction.replaceAll("_", " ")} · ${latestStrategyEvent.disposition.replaceAll("_", " ")}. This is an immutable research event, not a trade.` : "Completed-M5 strategy module observations will be journaled locally."}</p><code>{latestStrategyEvent?.reason_codes[0] ?? "APPEND_ONLY_RESEARCH_EVENTS"}</code></article>
      <article className="panel lower-card" hidden={activeView !== "validation"}><span className="eyebrow">PAPER VALIDATION</span><h2>{validation?.calibration_state ?? "CHECKING"}</h2><p>{validation ? `${validation.labelled_candidates}/${validation.paper_candidates} paper candidates have a fixed-horizon outcome label. Accuracy remains withheld until at least 30 labels.` : "Awaiting frozen completed-candle decisions."}</p><code>{validation?.reason_codes[0] ?? "CHRONOLOGICAL_LABELS_ONLY"}</code></article>
      <article className="panel lower-card" hidden={activeView !== "validation"}><span className="eyebrow">RESEARCH CONTROLS</span><h2>{operations?.kill_switch_enabled ? "PAPER STOPPED" : "PAPER RECORDING"}</h2><p>Manual promotion only. {operations?.daily_research_failure_count ?? 0} research job failures today. No real-money order execution exists in this application.</p><code>{operations?.alerts[0] ?? "NO_ORDER_EXECUTION"}</code></article>
      <article className="panel lower-card strategy-controls-card" hidden={activeView !== "settings"}><span className="eyebrow">STRATEGY CONTROLS</span><h2>Local rule enablement</h2><p>These switches only allow a completed-candle research vote to participate. They cannot create a trade or change historical evidence.</p><form onSubmit={(event) => event.preventDefault()}><label className="operator-token-field">Local operator token<input type="password" value={operatorToken} onChange={(event) => setOperatorToken(event.target.value)} autoComplete="off" placeholder="Required to save a change" /></label><ul className="strategy-settings-list">{strategySettings?.settings.map((setting) => <li key={setting.strategy_id}><div><strong>{setting.strategy_id.replaceAll("_", " ")}</strong><small>{setting.enabled ? "Enabled" : "Disabled"} · {setting.updated_at_utc ? `saved ${pht(setting.updated_at_utc)} PHT` : "default"}</small></div><button type="button" aria-pressed={setting.enabled} onClick={() => void toggleStrategy(setting.strategy_id, !setting.enabled)} disabled={updatingStrategy === setting.strategy_id}>{updatingStrategy === setting.strategy_id ? "Saving…" : setting.enabled ? "Disable" : "Enable"}</button></li>) ?? <li className="strategy-settings-empty">Choose an exact broker symbol to load strategy controls.</li>}</ul><code>OWNER_CONFIGURATION / NO_ORDER_EXECUTION</code></form></article>
      <article className="panel lower-card source-setup-card" hidden={activeView !== "settings"}><span className="eyebrow">SOURCE SETUP</span><div className="backtest-heading"><h2>{sourceCapabilities ? "Source capability check" : "Verify research sources"}</h2><button type="button" className="analyze-button" onClick={() => void checkSources()} disabled={checkingSources}>{checkingSources ? "Checking…" : "Check sources"}</button></div>{sourceCapabilities ? <><p>{m5Archive ? `${m5Archive.completed_candles} completed M5 candles retained from ${m5Archive.broker_server ?? "the active broker"} · ${m5Archive.readiness.replaceAll("_", " ")}.` : "No completed M5 archive has been retained for the active broker yet."}</p><ul className="source-capability-list">{sourceCapabilities.capabilities.map((capability) => <li key={capability.source_id}><div><strong>{capability.label}</strong><small>{capabilitySourceDetail(capability)}</small></div><span className={`source-state ${capability.state.toLowerCase()}`}>{capability.state.replaceAll("_", " ")}</span><p>{capability.summary}</p></li>)}</ul><code>{sourceCapabilities.reason_codes.join(" / ")}</code></> : <p>Run an on-demand source check. It reads local/public availability only and never stores provider credentials.</p>}</article>
      <article className="panel lower-card context-setup-card" hidden={activeView !== "settings"}><span className="eyebrow">CONTEXT SETUP</span><h2>Configure exact MT5 context symbols</h2><p>Enter only the exact symbols supplied by this connected broker. Saving checks each symbol against MT5 and adds a valid one to Market Watch. Blank fields clear that context feature; no alias is guessed or substituted.</p><form className="context-form" onSubmit={(event) => { event.preventDefault(); void saveCrossMarketContext(); }}>
        <div className="context-symbol-grid">
          <label>Dollar index <input name="dxy_symbol" value={contextDraft.dxy_symbol} onChange={(event) => setContextDraft((current) => ({ ...current, dxy_symbol: event.target.value }))} placeholder="Exact MT5 DXY symbol" autoComplete="off" /></label>
          <label>US Treasury yield <input name="us10y_symbol" value={contextDraft.us10y_symbol} onChange={(event) => setContextDraft((current) => ({ ...current, us10y_symbol: event.target.value }))} placeholder="Exact MT5 10Y-yield symbol" autoComplete="off" /></label>
          <label>Oil context <input name="wti_symbol" value={contextDraft.wti_symbol} onChange={(event) => setContextDraft((current) => ({ ...current, wti_symbol: event.target.value }))} placeholder="Exact MT5 oil symbol" autoComplete="off" /></label>
          <label>Volatility index or proxy <input name="volatility_symbol" value={contextDraft.volatility_symbol} onChange={(event) => setContextDraft((current) => ({ ...current, volatility_symbol: event.target.value }))} placeholder="Exact MT5 volatility symbol" autoComplete="off" /></label>
        </div>
        <div className="context-form-footer"><small>Cross-market features remain contextual research evidence only. They never create an order or trade instruction.</small><button type="submit" className="analyze-button" disabled={savingContext}>{savingContext ? "Saving…" : "Save context"}</button></div>
      </form></article>
      <SignalHistoryPanel history={signalHistory} error={moduleErrors.signalHistory ?? null} nowMs={now.getTime()} desktopPermission={desktopPermission} onEnableDesktopAlerts={() => void enableDesktopAlerts()} hidden={activeView !== "history"} />
      <article className="panel lower-card source-setup-card hfm-connection-card" aria-label="HFM account connection" hidden={activeView !== "settings"}>
        <span className="eyebrow">HFM ACCOUNT CONNECTION</span>
        <div className="backtest-heading">
          <h2>{hfmAccountStatus?.connected ? `HFM ${hfmAccountStatus.account_mode} CONNECTED` : "Connect your HFM account"}</h2>
          <button type="button" className="analyze-button" onClick={() => void checkHfmDemo()} disabled={checkingHfmDemo}>{checkingHfmDemo ? "Checking…" : "Check HFM connection"}</button>
        </div>
        <p>{hfmAccountStatus?.connected ? "The local MT5 terminal is signed in to an HFM trading account. PyonTrading can read this broker session for research only; it never places orders." : "Open your HFM client area to create or find a demo or real MT5 trading account. Then sign in to that trading account inside the local MT5 terminal using its account ID, password, and exact server."}</p>
        <div className="hfm-connection-actions">
          <a href="https://my.hfm.com/en/login" target="_blank" rel="noopener noreferrer">Open HFM account portal</a>
          <a href="https://www.hfm.com/int/en/platforms/mt5-how-to-connect" target="_blank" rel="noopener noreferrer">HFM MT5 sign-in guide</a>
        </div>
        <label className="hfm-account-choice">Account type to use<select value={targetHfmMode} onChange={(event) => setTargetHfmMode(event.target.value as "DEMO" | "LIVE")}><option value="DEMO">Demo account</option><option value="LIVE">Real account (research only)</option></select></label>
        <small>Switch saved accounts in the MT5 Navigator. This choice checks the active account; it does not sign in or switch MT5 for you.</small>
        {hfmAccountStatus?.connected && <div className="hfm-connection-details"><div><span>Account type</span><strong>{hfmAccountStatus.account_mode === "LIVE" ? "Real" : "Demo"}</strong></div><div><span>Active account</span><strong>{hfmAccountStatus.account_id_suffix ? `Account ending ${hfmAccountStatus.account_id_suffix}` : "ID unavailable"}</strong></div><div><span>MT5 server</span><strong>{hfmAccountStatus.broker_server}</strong></div></div>}
        {hfmAccountStatus?.connected && <p className={`hfm-selection-state ${targetHfmMode === hfmAccountStatus.account_mode ? "matched" : "mismatched"}`} role="status">{targetHfmMode === hfmAccountStatus.account_mode ? `Selected ${targetHfmMode === "DEMO" ? "demo" : "real"} account is active in MT5.` : `Selected ${targetHfmMode === "DEMO" ? "demo" : "real"} account is not active in MT5. Switch accounts in the MT5 Navigator.`} {targetHfmMode === "LIVE" ? "Real-account order automation is locked." : "Demo order automation is not enabled yet."}</p>}
        {hfmAccountStatus && !hfmAccountStatus.connected && <p className="hfm-connection-warning">{hfmAccountStatus.reason_codes.includes("HFM_BROKER_NOT_VERIFIED") ? "The active MT5 terminal is not verified as HFM. Sign in to your HFM trading account in MT5, then check again." : hfmAccountStatus.data_status === "DISCONNECTED" ? "MT5 is not connected. Open the desktop terminal and sign in, then check again." : `HFM connection unavailable: ${hfmAccountStatus.reason_codes.join(" / ")}.`}</p>}
        {hfmDemoStatus && <p className="hfm-demo-readiness">Optional demo safety binding: {hfmDemoStatus.ready ? "verified" : "not verified"}. {hfmDemoGuidance(hfmDemoStatus)}</p>}
        <small>HFM website sign-in manages accounts; the MT5 trading-account sign-in connects market data here. PyonTrading never asks for or stores your HFM password.</small>
        {hfmAccountStatus && <small>Checked {pht(hfmAccountStatus.observed_at_utc)} PHT. Rechecks every 10 seconds while this page is open.</small>}
        {hfmDemoError && <p className="module-error" role="alert">{hfmDemoError}</p>}
      </article>
    </section>
    </div>
    {newSignal && quoteFresh && connection?.terminal_connected && connection.data_status === "LIVE" && Date.parse(newSignal.expires_at_utc ?? "") > now.getTime() && <aside className="signal-alert" aria-label="New research signal" role="status">
      <span className="eyebrow">NEW SOURCE-CHECKED RESEARCH SIGNAL</span>
      <strong>{newSignal.decision.replace("_", " ")} · {newSignal.symbol}</strong>
      <p>Entry {newSignal.reference_levels ? newSignal.reference_levels.entry.toFixed(2) : "—"} · Stop {newSignal.reference_levels ? newSignal.reference_levels.stop_loss.toFixed(2) : "—"} · TP1 {newSignal.reference_levels ? newSignal.reference_levels.take_profit_1.toFixed(2) : "—"} · TP2 {newSignal.reference_levels ? newSignal.reference_levels.take_profit_2.toFixed(2) : "—"}</p>
      <small>Unvalidated research, not a win probability or order.</small>
      <div><button type="button" onClick={() => { navigateView("history"); setNewSignal(null); }}>View history</button><button type="button" onClick={() => setNewSignal(null)}>Dismiss</button></div>
    </aside>}
    {modalAnalysis && marketReviewView === "open" && <MarketReviewModal analysis={modalAnalysis} onClose={() => setMarketReviewView("closed")} onMinimize={() => setMarketReviewView("minimized")} />}
    {modalAnalysis && marketReviewView === "minimized" && <aside className="minimized-review" aria-label="Minimized market analysis">
      <div><span className="eyebrow">ANALYSIS READY</span><strong>{modalAnalysis.decision.replace("_", " ")}</strong></div>
      <button type="button" onClick={() => setMarketReviewView("open")}>Open</button>
      <button type="button" className="minimized-review-close" onClick={() => setMarketReviewView("closed")} aria-label="Close minimized market analysis">Close</button>
    </aside>}
  </main>;
}


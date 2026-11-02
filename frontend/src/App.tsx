import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ConnectionWizard } from "./components/ConnectionWizard";
import { LiveResearchWatch } from "./components/LiveResearchWatch";
import { MarketReviewModal } from "./components/MarketReviewModal";
import { PriceChart, type ChartOverlayKey, type ChartOverlays } from "./components/PriceChart";
import { api } from "./services/api";
import { age, pht, price, utc } from "./services/format";
import type { Backtest, BarEvent, Candles, ConfigurableStrategyId, Connection, Events, LiveEvent, LiveResearchWatch as LiveResearchWatchData, LocalSettings, MarketAnalysis, Operations, Quote, Research, SignalHistory, SignalJournal, SourceCapabilities, StrategyJournal, StrategySettings, ValidationSummary } from "./types/api";

const frames = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
const chartWindowLimits: Record<string, number> = { M1: 1441, M5: 289, M15: 97, M30: 49, H1: 25, H4: 7, D1: 2 };
const defaultChartOverlays: ChartOverlays = { trend: true, vwap: true, bands: false, activity: true };
const chartOverlayLabels: Record<ChartOverlayKey, string> = { trend: "EMA 20 / 60", vwap: "VWAP proxy", bands: "Bands 20,2", activity: "Tick activity" };
const LIVE_RESEARCH_REFRESH_MS = 5_000;
type WorkspaceView = "desk" | "research" | "validation" | "history" | "settings";
const workspaceViews: { id: WorkspaceView; label: string }[] = [
  { id: "desk", label: "Market desk" },
  { id: "research", label: "Research network" },
  { id: "validation", label: "Validation" },
  { id: "history", label: "History" },
  { id: "settings", label: "Sources & rules" },
];

function statusTone(status?: string) { return status === "LIVE" ? "good" : status === "DELAYED" ? "watch" : "danger"; }
function localEventTime(value: string | null) { return value ? new Intl.DateTimeFormat("en-PH", { weekday: "short", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Manila", hour12: true }).format(new Date(value)) : "Time unavailable"; }
export default function App() {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [candles, setCandles] = useState<Candles | null>(null);
  const [calendar, setCalendar] = useState<Events | null>(null);
  const [journal, setJournal] = useState<SignalJournal | null>(null);
  const [signalHistory, setSignalHistory] = useState<SignalHistory | null>(null);
  const [strategyJournal, setStrategyJournal] = useState<StrategyJournal | null>(null);
  const [strategySettings, setStrategySettings] = useState<StrategySettings | null>(null);
  const [operatorToken, setOperatorToken] = useState("");
  const [updatingStrategy, setUpdatingStrategy] = useState<ConfigurableStrategyId | null>(null);
  const [research, setResearch] = useState<Research | null>(null);
  const [liveWatch, setLiveWatch] = useState<LiveResearchWatchData | null>(null);
  const [validation, setValidation] = useState<ValidationSummary | null>(null);
  const [operations, setOperations] = useState<Operations | null>(null);
  const [modalAnalysis, setModalAnalysis] = useState<MarketAnalysis | null>(null);
  const [marketReviewView, setMarketReviewView] = useState<"open" | "minimized" | "closed">("closed");
  const [analyzingMarket, setAnalyzingMarket] = useState(false);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [runningBacktest, setRunningBacktest] = useState(false);
  const [sourceCapabilities, setSourceCapabilities] = useState<SourceCapabilities | null>(null);
  const [checkingSources, setCheckingSources] = useState(false);
  const [localSettings, setLocalSettings] = useState<LocalSettings | null>(null);
  const [contextDraft, setContextDraft] = useState({ dxy_symbol: "", us10y_symbol: "", wti_symbol: "", volatility_symbol: "" });
  const [savingContext, setSavingContext] = useState(false);
  const [timeframe, setTimeframe] = useState("M5");
  const [chartOverlays, setChartOverlays] = useState<ChartOverlays>(defaultChartOverlays);
  const [activeView, setActiveView] = useState<WorkspaceView>("desk");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(new Date());
  const latestSequence = useRef(0);
  const candleRequest = useRef(0);
  const snapshotRefreshInFlight = useRef(false);
  const researchRefreshInFlight = useRef(false);
  const currentTimeframe = useRef(timeframe);
  const contextDraftLoaded = useRef(false);
  const refreshCandlesRef = useRef<() => Promise<void>>(async () => {});
  const refreshSnapshotRef = useRef<() => Promise<void>>(async () => {});
  const refreshResearchRef = useRef<() => Promise<void>>(async () => {});

  const refreshCandles = useCallback(async () => {
    const requestId = ++candleRequest.current;
    try {
      const nextCandles = await api.candles(timeframe, chartWindowLimits[timeframe] ?? 300);
      if (requestId === candleRequest.current) setCandles(nextCandles);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "REQUEST_FAILED"); }
  }, [timeframe]);

  const refreshSnapshot = useCallback(async () => {
    if (snapshotRefreshInFlight.current) return;
    snapshotRefreshInFlight.current = true;
    try {
      const [currentConnection, currentQuote, currentCandles, currentCalendar, currentJournal, currentSignalHistory, currentStrategyJournal, currentStrategySettings, currentResearch, currentValidation, currentOperations, currentSettings] = await Promise.all([api.connection(), api.quote(), api.candles(timeframe, chartWindowLimits[timeframe] ?? 300), api.events("today"), api.signals(), api.signalHistory(), api.strategyJournal(), api.strategySettings(), api.research(), api.validation(), api.operations(), api.settings()]);
      setConnection(currentConnection); setQuote(currentQuote); setCandles(currentCandles); setCalendar(currentCalendar); setJournal(currentJournal); setSignalHistory(currentSignalHistory); setStrategyJournal(currentStrategyJournal); setStrategySettings(currentStrategySettings); setResearch(currentResearch); setLiveWatch(currentResearch.live_research_watch); setValidation(currentValidation); setOperations(currentOperations); setLocalSettings(currentSettings);
      if (!contextDraftLoaded.current) {
        setContextDraft({ dxy_symbol: currentSettings.dxy_symbol ?? "", us10y_symbol: currentSettings.us10y_symbol ?? "", wti_symbol: currentSettings.wti_symbol ?? "", volatility_symbol: currentSettings.volatility_symbol ?? "" });
        contextDraftLoaded.current = true;
      }
      setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "REQUEST_FAILED"); }
    finally { snapshotRefreshInFlight.current = false; setLoading(false); }
  }, [timeframe]);

  const refreshResearch = useCallback(async () => {
    if (snapshotRefreshInFlight.current || researchRefreshInFlight.current) return;
    researchRefreshInFlight.current = true;
    try {
      const currentResearch = await api.research();
      setResearch(currentResearch);
      setLiveWatch(currentResearch.live_research_watch);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "RESEARCH_REFRESH_FAILED");
    } finally {
      researchRefreshInFlight.current = false;
    }
  }, []);

  useEffect(() => { currentTimeframe.current = timeframe; refreshCandlesRef.current = refreshCandles; refreshSnapshotRef.current = refreshSnapshot; refreshResearchRef.current = refreshResearch; }, [refreshCandles, refreshResearch, refreshSnapshot, timeframe]);
  useEffect(() => { void refreshSnapshot(); }, [refreshSnapshot]);
  useEffect(() => { const id = window.setInterval(() => setNow(new Date()), 1_000); return () => window.clearInterval(id); }, []);
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
      socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/live`);
      socket.onopen = () => { retryDelay = 1_000; socket?.send("snapshot-ready"); void refreshSnapshotRef.current(); };
      socket.onmessage = (event) => {
        const update = JSON.parse(event.data) as LiveEvent;
        if (!Number.isInteger(update.sequence) || update.sequence <= latestSequence.current) return;
        latestSequence.current = update.sequence;
        if (update.type === "quote") {
          setQuote(update.payload as Quote);
          if (currentTimeframe.current !== "M5") void refreshCandlesRef.current();
        }
        if (update.type === "bar_update" && currentTimeframe.current === "M5") {
          const bar = update.payload as BarEvent;
          setCandles((current) => current?.timeframe === "M5" ? { ...current, data_status: bar.data_status, reason_codes: bar.reason_codes, observed_at_utc: update.observed_at_utc, candles: [...current.candles.slice(0, -1), bar.candle] } : current);
        }
        if (update.type === "bar_closed") {
          void refreshCandlesRef.current();
          void refreshResearchRef.current();
        }
        if (update.type === "provider_status") void refreshSnapshotRef.current();
      };
      socket.onclose = () => {
        if (stopped) return;
        retryTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 15_000);
      };
    };
    connect();
    return () => { stopped = true; if (retryTimer) window.clearTimeout(retryTimer); socket?.close(); };
  }, []);
  useEffect(() => { const id = window.setInterval(() => void refreshResearchRef.current(), LIVE_RESEARCH_REFRESH_MS); return () => window.clearInterval(id); }, []);

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
  const forming = candles?.candles.at(-1);
  const latestEvaluation = journal?.evaluations[0];
  const latestStrategyEvent = strategyJournal?.events[0];
  const todayEvents = calendar?.events ?? [];
  const bots = research?.bots ?? [];
  const botCoordination = useMemo(() => {
    const liveBots = bots.filter((bot) => bot.data_status === "LIVE" && bot.state !== "BLOCKED").length;
    const blockedBots = bots.filter((bot) => bot.state === "BLOCKED").length;
    const ensemble = research?.strategy_ensemble;
    return {
      totalBots: bots.length,
      liveBots,
      blockedBots,
      pendingBots: Math.max(bots.length - liveBots - blockedBots, 0),
      agreementCount: ensemble?.agreement_count ?? null,
      requiredAgreementCount: ensemble?.required_agreement_count ?? null,
      ensembleDecision: ensemble?.decision ?? null,
    };
  }, [bots, research]);
  const professional = research?.professional_analysis;
  const m5Archive = sourceCapabilities?.archives.find((archive) => archive.timeframe === "M5");
  const displayTime = useMemo(() => new Intl.DateTimeFormat("en-PH", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Asia/Manila", hour12: true }).format(now), [now]);
  const setupRequired = connection && (!connection.terminal_connected || !connection.configured_symbol);
  const activeOverlayCount = Object.values(chartOverlays).filter(Boolean).length;

  return <main className="workstation">
    <a className="skip-link" href="#market-desk">Skip to market desk</a>
    <header className="topbar">
      <div className="brand"><div className="brand-mark">P2</div><div><strong>PyonTrading</strong><span>READ-ONLY MARKET WORKSTATION</span></div></div>
      <div className="instrument"><span>INSTRUMENT</span><strong>{connection?.configured_symbol ?? "SYMBOL NOT SELECTED"}</strong><small>{connection?.broker_server ?? "MT5 connection required"}</small></div>
      <div className="quotes"><div><span>BID</span><strong>{price(quote?.bid ?? null)}</strong></div><div><span>ASK</span><strong>{price(quote?.ask ?? null)}</strong></div><div><span>SPREAD</span><strong>{quote?.spread_points === null || quote?.spread_points === undefined ? "—" : `${quote.spread_points.toFixed(1)} pt`}</strong></div></div>
      <div className="status-block" role="status"><span className={`status-dot ${statusTone(quote?.data_status ?? connection?.data_status)}`} /><div><strong>{quote?.data_status ?? connection?.data_status ?? "CONNECTING"}</strong><small>Observed: {pht(quote?.observed_at_utc ?? null)} PHT · {age(quote?.tick_age_seconds ?? null)}{quote?.timestamp_normalized ? ` · Broker clock +${(quote.broker_clock_offset_seconds ?? 0) / 3600}h normalized` : ""}</small></div></div>
      <div className="clock"><span>PHILIPPINES TIME</span><strong>{displayTime}</strong></div>
    </header>

    {error && <div className="error-strip" role="alert">Unable to refresh broker data: {error}. No price has been substituted.</div>}
    {loading && <div className="loading-strip">Checking local MT5 terminal…</div>}
    {setupRequired && <ConnectionWizard connection={connection} onRetry={() => void refreshSnapshot()} onSave={saveSymbol} />}
    <nav className="desk-navigation" aria-label="Workstation sections">
      <div className="desk-navigation-links">
        {workspaceViews.map((view) => <button key={view.id} type="button" className={activeView === view.id ? "active" : ""} aria-current={activeView === view.id ? "page" : undefined} onClick={() => setActiveView(view.id)}>{view.label}</button>)}
      </div>
      <span className="desk-boundary">Research only · no order execution</span>
    </nav>

    <section id="market-desk" className={`workspace-grid ${activeView === "research" ? "research-workspace" : "desk-workspace"}`} hidden={activeView !== "desk" && activeView !== "research"}>
      <section className="chart-panel panel" hidden={activeView !== "desk"}>
        <div className="panel-heading"><div><span className="eyebrow">BROKER CANDLE VIEW</span><h1>{connection?.configured_symbol ?? "XAUUSD"} <small>· {timeframe}</small></h1></div><div className="source-chip">MT5 · {candles?.data_status ?? "AWAITING"}</div></div>
        <div className="chart-context-line"><strong>24H broker-candle view</strong></div>
        <nav className="timeframes" aria-label="Chart timeframe">{frames.map((frame) => <button key={frame} className={frame === timeframe ? "selected" : ""} onClick={() => setTimeframe(frame)}>{frame}</button>)}</nav>
        <details className="chart-options"><summary>Indicators <span>{activeOverlayCount} active</span></summary><div className="chart-tools" aria-label="Chart overlay controls"><div>{(Object.keys(chartOverlayLabels) as ChartOverlayKey[]).map((overlay) => <button key={overlay} type="button" aria-pressed={chartOverlays[overlay]} onClick={() => toggleChartOverlay(overlay)}>{chartOverlayLabels[overlay]}</button>)}</div><small>Descriptive research context from completed broker candles.</small></div></details>
        {candles?.candles.length ? <><PriceChart candles={candles.candles} timeframe={timeframe} overlays={chartOverlays} /><div className="chart-footer"><span>Completed candles: {candles.candles.filter((candle) => candle.completed).length}</span><span className="forming">FORMING · {forming ? `${utc(forming.open_time_utc)} UTC` : "—"}</span><a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">Charting by TradingView</a></div></> : <div className="chart-empty"><div className="empty-icon">×</div><h2>No broker candles available</h2><p>{candles?.reason_codes[0] ?? "Connect MT5 and select your exact broker symbol to request real candles."}</p></div>}
      </section>

      <aside className={`research-panel panel ${activeView === "research" ? "research-view" : "desk-view"}`}>
        <LiveResearchWatch watch={liveWatch} coordination={botCoordination} onSaveReview={() => void analyzeMarket()} savingReview={analyzingMarket} />
        {/* Legacy manual summary intentionally removed: the live watch above is the single auto-refreshing status surface.
        <header className="research-summary">
          <div><span className="eyebrow">RESEARCH VERDICT</span><h2>{research?.market_state ?? analysis?.market_state ?? "DATA UNAVAILABLE"}</h2><p>{verdictSummary}</p></div>
          <button type="button" className="analyze-button" onClick={() => void analyzeMarket()} disabled={analyzingMarket}>{analyzingMarket ? "Analyzing…" : "Analyze market"}</button>
        </header>
        <div className="decision-facts" aria-label="Research status summary">
          <article><span>Data quality</span><strong>{research?.data_quality?.status ?? quote?.data_status ?? "CHECKING"}</strong><small>{research?.data_quality?.spread_state ?? "source pending"}</small></article>
          <article><span>Event risk</span><strong>{research?.event_risk_state?.replaceAll("_", " ") ?? "UNVERIFIED"}</strong><small>{nextEvent?.impact ? `${nextEvent?.impact} impact next` : "calendar status"}</small></article>
          <article><span>Rule agreement</span><strong>{ensemble ? `${ensemble.agreement_count}/${ensemble.required_agreement_count}` : "—"}</strong><small>{ensemble?.decision.replaceAll("_", " ") ?? `${liveBotCount}/${bots.length || "—"} bots live`}</small></article>
        </div>
        <details className="decision-details">
          <summary>Why this result</summary>
          <p>{analysis?.direction_context ?? "No verified quote or completed candle set is available."}</p>
          <ul className="gate-list">{analysis?.execution_gate.map((gate) => <li key={gate.label}><span className={gate.state === "PASS" ? "gate-pass" : gate.state === "WATCH" ? "gate-watch" : "gate-block"}>{gate.state}</span><div><strong>{gate.label}</strong><small>{gate.reason}</small></div></li>) ?? <li><span className="gate-block">WAIT</span><div><strong>Broker quote</strong><small>WAITING_FOR_MT5</small></div></li>}</ul>
          <div className="safety-note">Research signals only. This application never places orders.</div>
        </details>
        */}
        {activeView === "desk" && <button type="button" className="research-link" onClick={() => setActiveView("research")}>View research network <span>{bots.length} bot reports</span></button>}
        {activeView === "research" && <section className="bot-network" aria-label="Connected research bots">
          <div className="network-heading"><div><span className="eyebrow">CONNECTED RESEARCH BOTS</span><h2>{bots.length ? `${bots.length} source-backed observers` : "Waiting for research inputs"}</h2></div><strong>M5 / M15 / H1 / H4</strong></div>
          {bots.length ? bots.map((bot, index) => <details className={`bot-card ${bot.state.toLowerCase()}`} key={bot.bot_id}><summary><span className="bot-index">{String(index + 1).padStart(2, "0")}</span><span><strong>{bot.label}</strong><small>{bot.state.replaceAll("_", " ")} · {bot.data_status}</small></span><span className="bot-open-label">Details</span></summary><p>{bot.summary}</p>{bot.skills.length > 0 && <div className="bot-skills" aria-label={`${bot.label} skills`}>{bot.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>}{bot.facts.length > 0 && <ul className="bot-facts">{bot.facts.slice(0, 4).map((fact) => <li key={fact}>{fact}</li>)}</ul>}</details>) : <div className="bot-empty">Waiting for source-backed research inputs.</div>}
        </section>}
      </aside>
    </section>

    {activeView !== "desk" && activeView !== "research" && <header className="view-heading"><span className="eyebrow">WORKSTATION AREA</span><h2>{workspaceViews.find((view) => view.id === activeView)?.label}</h2><p>{activeView === "validation" ? "Chronological research, paper evidence, and source-labelled limitations." : activeView === "history" ? "Saved market reviews with their original source state." : "Local source, context, and rule configuration."}</p></header>}
    <section className={`lower-grid ${activeView}-grid`} hidden={activeView === "research"}>
      <article className="panel lower-card today-events-card" hidden={activeView !== "desk"}><span className="eyebrow">TODAY'S USD CALENDAR</span><h2>{calendar?.data_status ?? "CHECKING"}</h2>{todayEvents.length ? <ul className="today-events-list">{todayEvents.map((event) => <li key={`${event.title}-${event.event_time_utc}`}><span className={`impact impact-${event.impact.toLowerCase()}`}>{event.impact}</span><div><strong>{event.title}</strong><small>{localEventTime(event.event_time_manila)} PHT</small></div></li>)}</ul> : <p>{calendar?.data_status === "LIVE" ? "No remaining USD events in today's public export. This is not a no-news guarantee." : "Today's USD calendar is unavailable; news risk is unverified."}</p>}<code>{calendar?.reason_codes[0] ?? "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT"}</code></article>
      <article className="panel lower-card journal-card" hidden={activeView !== "desk"}><span className="eyebrow">LATEST OBSERVATION</span><h2>{latestEvaluation?.market_state ?? "Awaiting M5 close"}</h2><p>{latestEvaluation ? <>Completed M5 candle recorded {pht(latestEvaluation.candle_open_utc)} PHT. This is evidence, not a signal.</> : "Completed M5 observations are retained locally when the broker supplies them."}</p><code>{latestEvaluation?.reason_codes[0] ?? journal?.reason_codes[0] ?? "AWAITING_COMPLETED_CANDLE"}</code></article>
      <article className="panel lower-card backtest-card" hidden={activeView !== "validation"}><span className="eyebrow">BACKTESTING LAB</span><div className="backtest-heading"><h2>Historical M5 research</h2><button type="button" className="analyze-button" onClick={() => void runBacktest()} disabled={runningBacktest}>{runningBacktest ? "Running…" : "Run backtest"}</button></div>{backtest ? <><p>{backtest.completed_candles} completed broker candles examined. {backtest.limitation}</p><ul className="backtest-results">{backtest.results.map((result) => <li key={result.strategy_id}><strong>{result.strategy_id.replaceAll("_", " ")}</strong><span>{result.completed_trials} trials · {result.observed_signals} observed</span></li>)}</ul><code>{backtest.reason_codes.join(" / ")}</code></> : <p>Runs completed-candle research only. Results remain unavailable when broker history or execution-cost inputs are incomplete.</p>}</article>
      <article className="panel lower-card" hidden={activeView !== "validation"}><span className="eyebrow">VOLUME & ORDER FLOW</span><h2>{professional?.volume_source_category.replaceAll("_", " ") ?? "CHECKING"}</h2><p>{professional ? `VWAP: ${professional.volume_momentum.vwap_basis}. Profile: ${professional.volume_profile.state.replaceAll("_", " ")}. Genuine footprint/COMEX delta: ${professional.market_depth.source_category === "UNAVAILABLE" ? "unavailable" : "source retained"}.` : "Waiting for completed broker candles."}</p><code>{professional?.market_depth.reason_codes[0] ?? "SOURCE_CLASSIFICATION_PENDING"}</code></article>
      <article className="panel lower-card" hidden={activeView !== "validation"}><span className="eyebrow">STRATEGY JOURNAL</span><h2>{latestStrategyEvent?.state.replaceAll("_", " ") ?? "AWAITING M5 CLOSE"}</h2><p>{latestStrategyEvent ? `${latestStrategyEvent.strategy_id.replaceAll("_", " ")} · ${latestStrategyEvent.direction.replaceAll("_", " ")} · ${latestStrategyEvent.disposition.replaceAll("_", " ")}. This is an immutable research event, not a trade.` : "Completed-M5 strategy module observations will be journaled locally."}</p><code>{latestStrategyEvent?.reason_codes[0] ?? "APPEND_ONLY_RESEARCH_EVENTS"}</code></article>
      <article className="panel lower-card" hidden={activeView !== "validation"}><span className="eyebrow">PAPER VALIDATION</span><h2>{validation?.calibration_state ?? "CHECKING"}</h2><p>{validation ? `${validation.labelled_candidates}/${validation.paper_candidates} paper candidates have a fixed-horizon outcome label. Accuracy remains withheld until at least 30 labels.` : "Awaiting frozen completed-candle decisions."}</p><code>{validation?.reason_codes[0] ?? "CHRONOLOGICAL_LABELS_ONLY"}</code></article>
      <article className="panel lower-card" hidden={activeView !== "validation"}><span className="eyebrow">RESEARCH CONTROLS</span><h2>{operations?.kill_switch_enabled ? "PAPER STOPPED" : "PAPER RECORDING"}</h2><p>Manual promotion only. {operations?.daily_research_failure_count ?? 0} research job failures today. No real-money order execution exists in this application.</p><code>{operations?.alerts[0] ?? "NO_ORDER_EXECUTION"}</code></article>
      <article className="panel lower-card strategy-controls-card" hidden={activeView !== "settings"}><span className="eyebrow">STRATEGY CONTROLS</span><h2>Local rule enablement</h2><p>These switches only allow a completed-candle research vote to participate. They cannot create a trade or change historical evidence.</p><form onSubmit={(event) => event.preventDefault()}><label className="operator-token-field">Local operator token<input type="password" value={operatorToken} onChange={(event) => setOperatorToken(event.target.value)} autoComplete="off" placeholder="Required to save a change" /></label><ul className="strategy-settings-list">{strategySettings?.settings.map((setting) => <li key={setting.strategy_id}><div><strong>{setting.strategy_id.replaceAll("_", " ")}</strong><small>{setting.enabled ? "Enabled" : "Disabled"} · {setting.updated_at_utc ? `saved ${pht(setting.updated_at_utc)} PHT` : "default"}</small></div><button type="button" aria-pressed={setting.enabled} onClick={() => void toggleStrategy(setting.strategy_id, !setting.enabled)} disabled={updatingStrategy === setting.strategy_id}>{updatingStrategy === setting.strategy_id ? "Saving…" : setting.enabled ? "Disable" : "Enable"}</button></li>) ?? <li className="strategy-settings-empty">Choose an exact broker symbol to load strategy controls.</li>}</ul><code>OWNER_CONFIGURATION / NO_ORDER_EXECUTION</code></form></article>
      <article className="panel lower-card source-setup-card" hidden={activeView !== "settings"}><span className="eyebrow">SOURCE SETUP</span><div className="backtest-heading"><h2>{sourceCapabilities ? "Source capability check" : "Verify research sources"}</h2><button type="button" className="analyze-button" onClick={() => void checkSources()} disabled={checkingSources}>{checkingSources ? "Checking…" : "Check sources"}</button></div>{sourceCapabilities ? <><p>{m5Archive ? `${m5Archive.completed_candles} completed M5 candles retained from ${m5Archive.broker_server ?? "the active broker"} · ${m5Archive.readiness.replaceAll("_", " ")}.` : "No completed M5 archive has been retained for the active broker yet."}</p><ul className="source-capability-list">{sourceCapabilities.capabilities.map((capability) => <li key={capability.source_id}><div><strong>{capability.label}</strong><small>{capability.provider.replaceAll("_", " ")} · {capability.source_category.replaceAll("_", " ")}</small></div><span className={`source-state ${capability.state.toLowerCase()}`}>{capability.state.replaceAll("_", " ")}</span><p>{capability.summary}</p></li>)}</ul><code>{sourceCapabilities.reason_codes.join(" / ")}</code></> : <p>Run an on-demand source check. It reads local/public availability only and never stores provider credentials.</p>}</article>
      <article className="panel lower-card context-setup-card" hidden={activeView !== "settings"}><span className="eyebrow">CONTEXT SETUP</span><h2>Configure exact MT5 context symbols</h2><p>Enter only the exact symbols supplied by this connected broker. Saving checks each symbol against MT5 and adds a valid one to Market Watch. Blank fields clear that context feature; no alias is guessed or substituted.</p><form className="context-form" onSubmit={(event) => { event.preventDefault(); void saveCrossMarketContext(); }}>
        <div className="context-symbol-grid">
          <label>Dollar index <input value={contextDraft.dxy_symbol} onChange={(event) => setContextDraft((current) => ({ ...current, dxy_symbol: event.target.value }))} placeholder="Exact MT5 DXY symbol" autoComplete="off" /></label>
          <label>US Treasury yield <input value={contextDraft.us10y_symbol} onChange={(event) => setContextDraft((current) => ({ ...current, us10y_symbol: event.target.value }))} placeholder="Exact MT5 10Y-yield symbol" autoComplete="off" /></label>
          <label>Oil context <input value={contextDraft.wti_symbol} onChange={(event) => setContextDraft((current) => ({ ...current, wti_symbol: event.target.value }))} placeholder="Exact MT5 oil symbol" autoComplete="off" /></label>
          <label>Volatility index or proxy <input value={contextDraft.volatility_symbol} onChange={(event) => setContextDraft((current) => ({ ...current, volatility_symbol: event.target.value }))} placeholder="Exact MT5 volatility symbol" autoComplete="off" /></label>
        </div>
        <div className="context-form-footer"><small>Cross-market features remain contextual research evidence only. They never create an order or trade instruction.</small><button type="submit" className="analyze-button" disabled={savingContext}>{savingContext ? "Saving…" : "Save context"}</button></div>
      </form></article>
      <article className="panel lower-card signal-history-card" hidden={activeView !== "history"}><span className="eyebrow">SIGNAL HISTORY</span><h2>{signalHistory?.entries.length ? "Recent research results" : "No market reviews yet"}</h2><p>Every result returned by Analyze market is retained locally with its exact source state. These are research signals, never trade instructions.</p>{signalHistory?.entries.length ? <ul className="signal-history-list">{signalHistory.entries.map((entry) => <li key={entry.signal_id}><div><strong className={`history-decision ${entry.decision.toLowerCase()}`}>{entry.decision.replace("_", " ")}</strong><time>{pht(entry.provided_at_utc)} PHT</time></div><span>{entry.market_context.replaceAll("_", " ")} · {entry.data_status}</span><p>{entry.summary}</p><small>{entry.reason_codes.slice(0, 2).join(" / ")}</small></li>)}</ul> : <code>ANALYZE_MARKET_TO_CREATE_A_SOURCE_LABELLED_RECORD</code>}</article>
    </section>
    {modalAnalysis && marketReviewView === "open" && <MarketReviewModal analysis={modalAnalysis} onClose={() => setMarketReviewView("closed")} onMinimize={() => setMarketReviewView("minimized")} />}
    {modalAnalysis && marketReviewView === "minimized" && <aside className="minimized-review" aria-label="Minimized market analysis">
      <div><span className="eyebrow">ANALYSIS READY</span><strong>{modalAnalysis.decision.replace("_", " ")}</strong></div>
      <button type="button" onClick={() => setMarketReviewView("open")}>Open</button>
      <button type="button" className="minimized-review-close" onClick={() => setMarketReviewView("closed")} aria-label="Close minimized market analysis">Close</button>
    </aside>}
  </main>;
}


import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join, resolve } from "node:path";

const observed = "2026-10-22T11:00:00Z";

async function capturePhaseZeroBaseline(page: Page, projectName: string, name: string) {
  const capturePhase = process.env.CAPTURE_AFTER_REMEDIATION === "1"
    ? "after-remediation"
    : process.env.CAPTURE_PHASE0_BASELINE === "1"
      ? "phase0-baseline"
      : null;
  if (!capturePhase) return;
  const directory = resolve(process.cwd(), "..", "output", "playwright", capturePhase, projectName);
  await mkdir(directory, { recursive: true });
  await page.screenshot({ path: join(directory, `${name}.png`), fullPage: true });
}

const disconnected = {
  api_version: "v1", source: "MT5", source_timestamp_utc: null, observed_at_utc: observed,
  data_status: "DISCONNECTED", reason_codes: ["MT5_TERMINAL_NOT_AVAILABLE"], terminal_connected: false,
  terminal_path: null, broker_server: null, account_mode: "UNKNOWN", configured_symbol: null, gold_symbols: [],
};

const unavailableQuote = {
  api_version: "v1", source: "MT5", source_timestamp_utc: null, observed_at_utc: observed,
  data_status: "NOT_CONFIGURED", reason_codes: ["SYMBOL_NOT_SELECTED"], symbol: null, bid: null, ask: null,
  spread_price: null, spread_points: null, tick_age_seconds: null, digits: null,
};

const unavailableAnalysis = {
  api_version: "v1", source: "MT5", source_timestamp_utc: null, observed_at_utc: observed,
  data_status: "NOT_CONFIGURED", reason_codes: ["QUOTE_NOT_LIVE"], symbol: null, market_state: "DATA UNAVAILABLE",
  direction_context: "No verified quote or completed candle set is available.",
  execution_gate: [{ label: "Broker quote", state: "BLOCK", reason: "NOT_CONFIGURED" }],
};

const unavailableCandles = {
  api_version: "v1", source: "MT5", source_timestamp_utc: null, observed_at_utc: observed,
  data_status: "NOT_CONFIGURED", reason_codes: ["SYMBOL_NOT_SELECTED"], symbol: null, timeframe: "M5", candles: [],
};

const unavailableResearch = {
  api_version: "v1", source: "PYONTRADING2_RESEARCH_COORDINATOR", source_timestamp_utc: null, observed_at_utc: observed,
  data_status: "NOT_CONFIGURED", reason_codes: ["QUOTE_NOT_LIVE"], symbol: null, research_window_hours: 12,
  market_state: "DATA UNAVAILABLE", validation_state: "NOT_VALIDATED", analysis_timeframes: [], bots: [], evidence_observations: 0,
  data_quality: null, session_regime: null, cross_market: [], official_macro_sources: [], event_risk_state: "UNVERIFIED", strategy_ensemble: null, operations: null,
};

const validation = {
  symbol: "XAUUSD", total_frozen_decisions: 0, paper_candidates: 0, labelled_candidates: 0,
  directional_matches: 0, accuracy_percent: null, calibration_state: "INSUFFICIENT_LABELS",
  walk_forward: {}, regime_counts: {}, maximum_drawdown_points: null, cost_status: "COSTS_INCOMPLETE",
  reason_codes: ["NO_ORDER_EXECUTION"],
};

const operations = {
  kill_switch_enabled: false, research_pipeline_enabled: true, model_promotion_state: "REVIEW_REQUIRED", daily_research_failure_count: 0,
  alerts: [], latest_audit_at_utc: null, reason_codes: ["NO_ORDER_EXECUTION"],
};

const professional = {
  volume_source_category: "BROKER_TICK_PROXY",
  liquidity_sweep: { source_category: "BROKER_TICK_PROXY", data_status: "LIVE", state: "OBSERVING", direction: null, swept_level: null, absorption_state: "UNAVAILABLE_NO_EXECUTED_FLOW", reason_codes: ["NO_COMPLETED_CANDLE_SWEEP"] },
  volume_momentum: { source_category: "BROKER_TICK_PROXY", data_status: "LIVE", vwap: 4075.1, vwap_basis: "TYPICAL_PRICE_WEIGHTED_BY_BROKER_TICK_ACTIVITY", relative_activity_ratio: 1.2, relative_activity_basis: "SAME_UTC_TIME_OF_DAY_MEDIAN", adx_14: 27.6, state: "ARMED", direction: "BEARISH", reason_codes: ["BROKER_TICK_ACTIVITY_NOT_EXECUTED_VOLUME"] },
  estimated_order_flow: { source_category: "ESTIMATED_DELTA", data_status: "LIVE", estimated_bar_delta: -12, session_cvd: -102, session_reset_basis: "UTC_DAY", divergence: "NONE", reason_codes: ["NOT_GENUINE_FUTURES_ORDER_FLOW"] },
  volume_profile: { source_category: "BROKER_TICK_PROXY", data_status: "LIVE", profile_basis: "COMPLETED_BAR_CLOSE_BUCKETED_BROKER_TICK_ACTIVITY", point_of_control: 4075, value_area_high: 4079, value_area_low: 4071, high_volume_nodes: [4075], low_volume_nodes: [4071], state: "DEVELOPING_PROXY", reason_codes: ["CLOSE_BUCKET_PROXY_NOT_VOLUME_AT_PRICE"] },
  opening_range: { data_status: "LIVE", session: "NEW_YORK", range_high: 4080, range_low: 4070, state: "OBSERVING", direction: null, reason_codes: ["COMPLETED_CANDLES_ONLY"] },
  market_depth: { source_category: "UNAVAILABLE", data_status: "NOT_CONFIGURED", broker_depth_available: false, level_count: 0, summary: "No licensed futures depth source.", reason_codes: ["NOT_CONSOLIDATED_FUTURES_DEPTH"] },
  strategy_modules: [
    { strategy_id: "LIQUIDITY_SWEEP_REVERSAL", strategy_version: "liquidity-sweep-reversal-v1", state: "OBSERVING", direction: "ABSTAIN", data_sources: ["BROKER_TICK_PROXY"], summary: "Sweep research.", reason_codes: [] },
    { strategy_id: "VWAP_VOLUME_MOMENTUM", strategy_version: "vwap-tick-proxy-momentum-v1", state: "ARMED", direction: "WATCH_SHORT", data_sources: ["BROKER_TICK_PROXY"], summary: "Tick activity proxy.", reason_codes: [] },
    { strategy_id: "ESTIMATED_ORDER_FLOW", strategy_version: "estimated-delta-proxy-v1", state: "OBSERVING", direction: "ABSTAIN", data_sources: ["ESTIMATED_DELTA"], summary: "Not genuine flow.", reason_codes: [] },
    { strategy_id: "OPENING_RANGE_BREAKOUT", strategy_version: "session-opening-range-v1", state: "OBSERVING", direction: "ABSTAIN", data_sources: ["BROKER_TICK_PROXY"], summary: "Opening range.", reason_codes: [] },
    { strategy_id: "VOLUME_PROFILE_AUCTION", strategy_version: "close-bucket-tick-proxy-profile-v1", state: "OBSERVING", direction: "ABSTAIN", data_sources: ["BROKER_TICK_PROXY"], summary: "Profile proxy.", reason_codes: [] },
    { strategy_id: "MARKET_DEPTH", strategy_version: "broker-depth-provenance-v1", state: "UNAVAILABLE", direction: "ABSTAIN", data_sources: ["UNAVAILABLE"], summary: "Depth unavailable.", reason_codes: [] },
    { strategy_id: "CROSS_MARKET_CONTEXT", strategy_version: "configured-context-v1", state: "UNAVAILABLE", direction: "ABSTAIN", data_sources: [], summary: "Context unavailable.", reason_codes: [] },
  ],
  risk_engine: { state: "REVIEW_REQUIRED", lifecycle_state: "OBSERVING", contract_specifications_available: true, quote_freshness_available: true, spread_available: true, event_risk_clear: true, costs_complete: false, reason_codes: ["COMMISSION_UNAVAILABLE", "NO_ORDER_EXECUTION"] },
  coordinator_state: "NO_TRADE", reason_codes: ["NO_EXECUTED_FUTURES_FLOW", "NO_ORDER_EXECUTION"],
};

const liveConnection = {
  ...disconnected, data_status: "LIVE", reason_codes: [], terminal_connected: true, account_mode: "DEMO",
  broker_server: "MetaQuotes-Demo", configured_symbol: "XAUUSD", gold_symbols: [{ name: "XAUUSD", visible: true }],
};

const liveQuote = {
  ...unavailableQuote, source_timestamp_utc: observed, data_status: "LIVE", reason_codes: ["MT5_QUOTE_CURRENT"],
  symbol: "XAUUSD", bid: 4077.75, ask: 4078.15, spread_price: 0.4, spread_points: 40, tick_age_seconds: 0.2, digits: 2,
};

const liveAnalysis = {
  ...unavailableAnalysis, source_timestamp_utc: observed, data_status: "LIVE", reason_codes: ["NO_ORDER_EXECUTION"],
  symbol: "XAUUSD", market_state: "NO TRADE", direction_context: "Completed broker candles are available; no execution logic is enabled.",
  execution_gate: [{ label: "Broker quote", state: "PASS", reason: "LIVE" }],
};

const liveCandles = {
  ...unavailableCandles, source_timestamp_utc: observed, data_status: "LIVE", reason_codes: ["COMPLETED_CANDLES_ONLY"], symbol: "XAUUSD",
  candles: [{ open_time_utc: "2026-10-22T10:55:00Z", open: 4076.5, high: 4078.5, low: 4076.2, close: 4077.75, tick_volume: 12, completed: false }],
};

const liveResearch = {
  ...unavailableResearch, source_timestamp_utc: observed, data_status: "LIVE", reason_codes: ["NO_ORDER_EXECUTION"], symbol: "XAUUSD",
  market_state: "NO TRADE", evidence_observations: 56,
  analysis_timeframes: [
    { timeframe: "M5", window_label: "12h", required_completed_candles: 144, completed_candles: 144, data_status: "LIVE", source_timestamp_utc: observed, structure: "DOWNWARD_STRUCTURE", indicators: { ema_20: 4078.3, ema_60: 4085.61, rsi_14: 23.4, atr_14: 4.87, macd_histogram: -2.626, adx_14: 27.6, range_position_percent: 5.4, latest_structure_event: "BEARISH CHOCH", active_fair_value_gaps: 9 }, reason_codes: ["COMPLETED_CANDLES_ONLY"] },
    { timeframe: "M15", window_label: "24h", required_completed_candles: 96, completed_candles: 96, data_status: "LIVE", source_timestamp_utc: observed, structure: "DOWNWARD_STRUCTURE", reason_codes: ["COMPLETED_CANDLES_ONLY"] },
    { timeframe: "H1", window_label: "3d", required_completed_candles: 72, completed_candles: 72, data_status: "LIVE", source_timestamp_utc: observed, structure: "DOWNWARD_STRUCTURE", reason_codes: ["COMPLETED_CANDLES_ONLY"] },
    { timeframe: "H4", window_label: "10d", required_completed_candles: 60, completed_candles: 60, data_status: "LIVE", source_timestamp_utc: observed, structure: "DOWNWARD_STRUCTURE", reason_codes: ["COMPLETED_CANDLES_ONLY"] },
  ],
  bots: [
    { bot_id: "quality", label: "Data quality sentinel", source: "MT5", source_url: null, data_status: "LIVE", state: "OBSERVING", source_timestamp_utc: observed, updated_at_utc: observed, summary: "Integrity clear.", skills: [], facts: ["No candle gaps"], reason_codes: [], evidence_count: 0 },
    { bot_id: "chart", label: "Chart analyst", source: "MT5", source_url: null, data_status: "LIVE", state: "OBSERVING", source_timestamp_utc: observed, updated_at_utc: observed, summary: "Completed multi-timeframe broker candles available.", skills: [], facts: ["M5: 144/144 completed"], reason_codes: [], evidence_count: 56 },
    { bot_id: "momentum", label: "Momentum analyst", source: "MT5", source_url: null, data_status: "LIVE", state: "OBSERVING", source_timestamp_utc: observed, updated_at_utc: observed, summary: "Momentum measured.", skills: [], facts: ["ADX 27"], reason_codes: [], evidence_count: 0 },
    { bot_id: "calendar", label: "Macro & event watcher", source: "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT", source_url: "https://www.forexfactory.com/calendar", data_status: "LIVE", state: "WATCHING", source_timestamp_utc: observed, updated_at_utc: observed, summary: "USD calendar is current.", skills: [], facts: ["Event-risk horizon clear"], reason_codes: [], evidence_count: 0 },
    { bot_id: "context", label: "Cross-market context", source: "MT5_CONFIGURED_CONTEXT", source_url: null, data_status: "NOT_CONFIGURED", state: "OBSERVING", source_timestamp_utc: null, updated_at_utc: observed, summary: "Context not configured.", skills: [], facts: ["No symbols"], reason_codes: [], evidence_count: 0 },
    { bot_id: "strategy", label: "Strategy ensemble & abstention", source: "PYONTRADING2", source_url: null, data_status: "LIVE", state: "COLLECTING_EVIDENCE", source_timestamp_utc: observed, updated_at_utc: observed, summary: "Validation remains required.", skills: [], facts: ["No execution"], reason_codes: ["NO_ORDER_EXECUTION"], evidence_count: 56 },
  ],
  data_quality: { status: "CLEAR", quote_status: "LIVE", tick_age_seconds: 0.2, spread_points: 40, spread_baseline_points: 35, spread_state: "NORMAL", candle_gap_count: 0, timestamp_normalized: false, broker_clock_offset_seconds: 0, broker_session_state: "LIVE_QUOTE", checked_at_utc: observed, reason_codes: [] },
  session_regime: { session_label: "NEW_YORK", session_timezone_basis: "IANA_MARKET_SESSION_TIMEZONES", volatility_regime: "NORMAL", market_regime: "TREND", spread_state: "NORMAL", observed_at_utc: observed, reason_codes: [] },
  cross_market: [], official_macro_sources: [], event_risk_state: "CLEAR",
  strategy_ensemble: { decision: "NO_TRADE", confidence_state: "WITHHELD", agreement_count: 1, required_agreement_count: 2, model_promotion_state: "REVIEW_REQUIRED", votes: [], reason_codes: ["NO_ORDER_EXECUTION"] },
  professional_analysis: professional,
  operations,
};

const marketReview = {
  api_version: "v1", source: "PYONTRADING2_RESEARCH_SCREEN", source_timestamp_utc: observed, observed_at_utc: observed,
  data_status: "LIVE", reason_codes: ["RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES", "NO_ORDER_EXECUTION"], symbol: "XAUUSD",
  analysis_mode: "RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES", decision: "NO_TRADE", market_context: "DOWNWARD_STRUCTURE",
  summary: "No trade: evidence is research-only.", gates: [{ label: "Broker quote", state: "PASS", reason: "LIVE" }],
  analysis_timeframes: liveResearch.analysis_timeframes, supporting_facts: ["Completed candles only."],
  data_quality: liveResearch.data_quality, session_regime: liveResearch.session_regime, cross_market: [], official_macro_sources: [], event_risk_state: "CLEAR",
  strategy_ensemble: { ...liveResearch.strategy_ensemble, votes: [{ strategy_id: "STRUCTURE_ALIGNMENT", strategy_version: "structure-alignment-v1", decision: "WATCH_SHORT", reason_codes: [] }, { strategy_id: "MOMENTUM_ALIGNMENT", strategy_version: "momentum-alignment-v1", decision: "ABSTAIN", reason_codes: [] }, { strategy_id: "RANGE_BREAKOUT", strategy_version: "range-breakout-v2", decision: "ABSTAIN", reason_codes: [] }] },
  professional_analysis: professional,
  paper_trading: { status: "NOT_CREATED", candidate_id: null, expected_spread_points: 40, commission_points: null, slippage_points: null, fill_quality_state: "NOT_APPLICABLE", reason_codes: ["NO_ORDER_EXECUTION"] },
};

const liveWatch = {
  api_version: "v1", source: "PYONTRADING2_LIVE_RESEARCH_WATCH", source_timestamp_utc: observed, observed_at_utc: observed,
  data_status: "LIVE", reason_codes: ["AUTOMATIC_LIVE_RESEARCH_WATCH", "EVIDENCE_SCORE_NOT_PROBABILITY", "NO_ORDER_EXECUTION"], symbol: "XAUUSD",
  lifecycle: "WITHHELD", direction: "NONE", evidence_score: 75, evidence_score_basis: "EVIDENCE_COVERAGE_NOT_PROBABILITY",
  research_horizon: "UNAVAILABLE", horizon_basis: "NO_ACTIVE_DIRECTIONAL_RESEARCH_WATCH", horizon_review_at_utc: null,
  horizon_reason_codes: ["NO_ACTIVE_DIRECTIONAL_RESEARCH_WATCH"],
  active_from_utc: observed, scheduled_review_at_utc: "2026-10-22T01:05:00Z", expires_at_utc: "2026-10-22T01:05:00Z",
  summary: "Automatic research watch is withheld because the deterministic readers or safety gates do not currently support a directional research watch.",
  invalidation_conditions: ["Independent completed-candle rules must reach the required agreement.", "A newer completed M5 candle triggers the next deterministic review."],
  gates: [{ label: "Broker quote", state: "PASS", reason: "LIVE" }, { label: "Event-risk horizon", state: "PASS", reason: "CLEAR" }],
  analysis_timeframes: liveResearch.analysis_timeframes, data_quality: liveResearch.data_quality, event_risk_state: "CLEAR", strategy_ensemble: liveResearch.strategy_ensemble,
};

const unavailableLiveWatch = {
  ...liveWatch, source_timestamp_utc: null, data_status: "NOT_CONFIGURED", reason_codes: ["SYMBOL_NOT_SELECTED", "AUTOMATIC_LIVE_RESEARCH_WATCH", "NO_ORDER_EXECUTION"], symbol: null,
  lifecycle: "UNAVAILABLE", direction: "NONE", evidence_score: 0, active_from_utc: null, scheduled_review_at_utc: null, expires_at_utc: null,
  summary: "Automatic research watch is unavailable because a required source or completed M5 evidence window is unavailable.",
  invalidation_conditions: ["Broker quote: NOT_CONFIGURED", "Completed M5 / M15 / H1 / H4 evidence: NOT_CONFIGURED"],
  gates: [{ label: "Broker quote", state: "BLOCK", reason: "NOT_CONFIGURED" }], analysis_timeframes: [], data_quality: null, event_risk_state: "UNVERIFIED", strategy_ensemble: null,
};

const events = { api_version: "v1", source: "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT", source_timestamp_utc: observed, observed_at_utc: observed, data_status: "LIVE", reason_codes: [], source_url: "https://www.forexfactory.com/calendar", events: [] };
const journal = { api_version: "v1", source: "PYONTRADING2", source_timestamp_utc: observed, observed_at_utc: observed, data_status: "LIVE", reason_codes: [], evaluations: [] };
const strategyJournal = { api_version: "v1", source: "PYONTRADING2_STRATEGY_JOURNAL", source_timestamp_utc: observed, observed_at_utc: observed, data_status: "LIVE", reason_codes: ["NO_ORDER_EXECUTION"], events: [] };
const strategySettings = {
  api_version: "v1", source: "PYONTRADING2_LOCAL_STRATEGY_SETTINGS", source_timestamp_utc: observed, observed_at_utc: observed,
  data_status: "LIVE", reason_codes: ["LOCAL_OWNER_CONFIGURATION", "NO_ORDER_EXECUTION"], symbol: "XAUUSD",
  settings: [
    { strategy_id: "STRUCTURE_ALIGNMENT", enabled: true, updated_at_utc: null },
    { strategy_id: "MOMENTUM_ALIGNMENT", enabled: true, updated_at_utc: null },
    { strategy_id: "RANGE_BREAKOUT", enabled: true, updated_at_utc: null },
  ],
};
const signalHistory = {
  api_version: "v1", source: "PYONTRADING2_SIGNAL_HISTORY", source_timestamp_utc: observed, observed_at_utc: observed, data_status: "LIVE", reason_codes: ["USER_REQUESTED_RESEARCH_HISTORY", "NO_ORDER_EXECUTION"],
  entries: [{ signal_id: "signal-history-1", provided_at_utc: observed, symbol: "XAUUSD", source: "PYONTRADING2_RESEARCH_SCREEN", source_timestamp_utc: observed, data_status: "LIVE", analysis_mode: "RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES", decision: "NO_TRADE", market_context: "DOWNWARD_STRUCTURE", summary: "History keeps this source-labelled research result.", event_risk_state: "CLEAR", paper_status: "NOT_CREATED", input_fingerprint: "history-fingerprint", reason_codes: ["NO_ORDER_EXECUTION"] }],
};
const localSettings = {
  symbol: "XAUUSD", timezone: "Asia/Manila", max_risk_percent: 0.5,
  dxy_symbol: null, us10y_symbol: null, wti_symbol: null, volatility_symbol: null,
};
const sourceCapabilities = {
  api_version: "v1", source: "PYONTRADING2_SOURCE_SETUP", source_timestamp_utc: observed, observed_at_utc: observed, data_status: "LIVE", symbol: "XAUUSD", reason_codes: ["CAPABILITY_CHECK_ON_DEMAND", "NO_CREDENTIAL_STORAGE", "NO_ORDER_EXECUTION"],
  archives: [{ source: "MT5", broker_server: "MetaQuotes-Demo", symbol: "XAUUSD", timeframe: "M5", completed_candles: 240, first_open_utc: "2026-10-21T15:00:00Z", latest_open_utc: observed, observed_span_days: 1, readiness: "COLLECTING", reason_codes: ["ARCHIVE_WINDOW_COLLECTING"] }],
  capabilities: [
    { source_id: "MT5_TERMINAL", label: "MT5 terminal", data_status: "LIVE", state: "READY", source_category: "UNAVAILABLE", provider: "LOCAL_META_TRADER_5", summary: "Terminal available.", setup_hint: "Keep it open.", reason_codes: [] },
    { source_id: "BROKER_CANDLES", label: "Broker candles", data_status: "LIVE", state: "READY", source_category: "UNAVAILABLE", provider: "MT5_BROKER_TERMINAL", summary: "Candles available.", setup_hint: "Wait for completed bars.", reason_codes: [] },
    { source_id: "BROKER_TICK_ACTIVITY", label: "Broker tick activity", data_status: "LIVE", state: "READY", source_category: "BROKER_TICK_PROXY", provider: "MT5_BROKER_TERMINAL", summary: "Tick proxy only.", setup_hint: "No executed volume.", reason_codes: [] },
    { source_id: "BROKER_DEPTH", label: "Broker depth", data_status: "NOT_CONFIGURED", state: "UNAVAILABLE", source_category: "UNAVAILABLE", provider: "MT5_BROKER_TERMINAL", summary: "Depth unavailable.", setup_hint: "Broker-specific.", reason_codes: [] },
    { source_id: "USD_CALENDAR", label: "USD calendar", data_status: "LIVE", state: "READY", source_category: "UNAVAILABLE", provider: "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT", summary: "Calendar available.", setup_hint: "Informational.", reason_codes: [] },
    { source_id: "CROSS_MARKET_CONTEXT", label: "Cross-market context", data_status: "NOT_CONFIGURED", state: "ACTION_REQUIRED", source_category: "UNAVAILABLE", provider: "MT5_CONFIGURED_CONTEXT", summary: "No context symbols.", setup_hint: "Configure exact broker symbols.", reason_codes: [] },
    { source_id: "LICENSED_FUTURES_FLOW", label: "Licensed futures order flow", data_status: "NOT_CONFIGURED", state: "ACTION_REQUIRED", source_category: "UNAVAILABLE", provider: "NO_PROVIDER_CONFIGURED", summary: "No licensed futures provider is configured.", setup_hint: "Choose a provider.", reason_codes: ["NO_SYNTHETIC_ORDER_FLOW"] },
  ],
};

async function mockSnapshot(page: Page, values: { connection: object; quote: object; analysis: object; candles: object; research: object; liveWatch?: object; }) {
  let settings = { ...localSettings };
  await page.route("**/api/connection", (route) => route.fulfill({ json: values.connection }));
  await page.route("**/api/quote", (route) => route.fulfill({ json: values.quote }));
  await page.route("**/api/analysis", (route) => route.fulfill({ json: values.analysis }));
  await page.route("**/api/candles**", (route) => route.fulfill({ json: values.candles }));
  await page.route("**/api/events?scope=today", (route) => route.fulfill({ json: events }));
  await page.route("**/api/signals", (route) => route.fulfill({ json: journal }));
  await page.route("**/api/signals/history", (route) => route.fulfill({ json: signalHistory }));
  await page.route("**/api/strategy-journal", (route) => route.fulfill({ json: strategyJournal }));
  await page.route("**/api/research/strategies", (route) => route.fulfill({ json: strategySettings }));
  await page.route("**/api/research", (route) => route.fulfill({ json: { ...values.research, live_research_watch: { ...(values.liveWatch ?? liveWatch), observed_at_utc: new Date().toISOString() } } }));
  await page.route("**/api/research/validation", (route) => route.fulfill({ json: validation }));
  await page.route("**/api/research/operations", (route) => route.fulfill({ json: operations }));
  await page.route("**/api/sources/capabilities", (route) => route.fulfill({ json: sourceCapabilities }));
  await page.route("**/api/market/scan", (route) => route.fulfill({ json: { data_status: "HISTORY_INSUFFICIENT", observed_at_utc: observed, instruments: [], currency_strength: [], correlations: [], reason_codes: [] } }));
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "PUT") settings = { ...settings, ...JSON.parse(route.request().postData() ?? "{}") };
    await route.fulfill({ json: settings });
  });
}

test("desktop market desk fits the chart, setup and support cards in the viewport", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  const pendingWatch = { ...liveWatch, lifecycle: "ACTIVE_RESEARCH_WATCH", direction: "SHORT_CONTEXT", reference_levels: null,
    expires_at_utc: new Date(Date.now() + 300_000).toISOString(), scheduled_review_at_utc: new Date(Date.now() + 300_000).toISOString(),
    reference_levels_reason: "TOP_DOWN_CONFIRMATION_REQUIRED", research_horizon: "MULTI_SESSION_CONTEXT",
    data_quality: { ...liveWatch.data_quality, status: "WATCH", candle_gap_count: 1 },
    top_down: { state: "REJECTED", observed_at_utc: new Date().toISOString(), stages: [
      { stage: "TRIGGER", required: true, state: "REJECTED", timeframes: ["M5"], evidence_timestamps: {}, reason_codes: [] },
      { stage: "RISK", required: true, state: "REJECTED", timeframes: [], evidence_timestamps: {}, reason_codes: [] },
    ] },
    signal_proof: { publication_state: "WITHHELD", performance_state: "UNVALIDATED", checks: [
      { code: "DATA_QUALITY_CLEAR", passed: false, detail: "Integrity clear and spread within observed range" },
    ] },
  };
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch, liveWatch: pendingWatch });
  await page.route("**/api/quote", (route) => route.fulfill({ json: { ...liveQuote, observed_at_utc: new Date().toISOString() } }));
  await page.route("**/api/research", (route) => route.fulfill({ json: { ...liveResearch, live_research_watch: {
    ...pendingWatch, observed_at_utc: new Date().toISOString(), top_down: { ...pendingWatch.top_down, observed_at_utc: new Date().toISOString() },
  } } }));
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1366, height: 768 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "SHORT SETUP PENDING", exact: true })).toBeVisible({ timeout: 10_000 });
    const main = await page.locator(".workstation").boundingBox();
    const chart = await page.locator(".chart-canvas").boundingBox();
    const panel = await page.locator(".desk-workspace .desk-view").boundingBox();
    const save = await page.getByRole("button", { name: "Save review snapshot" }).boundingBox();
    expect(main!.x).toBeLessThanOrEqual(16);
    expect(main!.x + main!.width).toBeGreaterThanOrEqual(viewport.width - 16);
    expect(chart!.height).toBeGreaterThanOrEqual(viewport.height * 0.40);
    expect(panel!.y + panel!.height).toBeLessThanOrEqual(viewport.height - 4);
    expect(save!.y + save!.height).toBeLessThanOrEqual(viewport.height - 8);
    await expect(page.getByRole("button", { name: "Save review snapshot" })).toBeInViewport({ ratio: 1 });
    await expect(page.getByRole("button", { name: "View research network", exact: false })).toBeInViewport({ ratio: 1 });
    await expect(page.getByRole("group", { name: "Detailed research review" }).locator("summary").first()).toBeInViewport({ ratio: 1 });
    await expect(page.locator(".today-events-card")).toBeInViewport({ ratio: 1 });
    await expect(page.locator(".journal-card")).toBeInViewport({ ratio: 1 });
    const chartPanel = await page.locator(".chart-panel").boundingBox();
    const calendarCard = await page.locator(".today-events-card").boundingBox();
    const observation = await page.locator(".journal-card").boundingBox();
    const review = await page.locator(".watch-review").boundingBox();
    expect(Math.abs(calendarCard!.x - chartPanel!.x)).toBeLessThan(1);
    expect(Math.abs(calendarCard!.width - chartPanel!.width)).toBeLessThan(1);
    expect(Math.abs(observation!.x - panel!.x)).toBeLessThan(1);
    expect(save!.y - (review!.y + review!.height)).toBeLessThan(35);
    expect(await page.locator(".live-research-watch").evaluate((element) => element.scrollHeight - element.clientHeight)).toBeLessThanOrEqual(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
  }
});

test("the clock updates the active session and overlap without a reload", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-11-16T07:59:59Z") });
  await page.clock.pauseAt(new Date("2026-11-16T07:59:59Z"));
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.goto("/");
  const session = page.getByRole("status", { name: "Current trading session" });
  await expect(session).toContainText("Tokyo");
  await expect(session).not.toContainText("London");
  await page.clock.fastForward(2_000);
  await expect(session).toContainText("Tokyo + London");
  await expect(session).toContainText("OVERLAP");
  await page.clock.setSystemTime(new Date("2026-11-21T12:00:00Z"));
  await page.clock.runFor(1_000);
  await expect(session).toContainText("Weekend");
  await expect(session).toBeInViewport({ ratio: 1 });
});

test("the desk keeps validation detail out of the default decision view but accessible on demand", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.goto("/");
  const review = page.getByRole("group", { name: "Detailed research review" });
  await expect(review).toBeVisible();
  await expect(review).not.toHaveAttribute("open");
  await expect(page.locator(".watch-bot-line")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Save review snapshot" })).toBeVisible();
  await review.locator("summary").first().click();
  await expect(page.locator(".watch-bot-line")).toBeVisible();
  await expect(page.getByLabel("Research conditions")).toBeVisible();
  await review.locator("summary").first().focus();
  await page.keyboard.press("Enter");
  await expect(review).not.toHaveAttribute("open");
});

test("research scanner shows comparative context and handles a refresh failure", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/market/scan", (route) => route.fulfill({ json: {
    data_status: "LIVE", observed_at_utc: observed, source_timestamp_utc: observed,
    instruments: [{ symbol: "EURUSD.x", base_currency: "EUR", quote_currency: "USD", data_status: "LIVE", comparison_rank: 1, return_20_bars_percent: 0.25, atr_percent: 0.08, spread_atr_ratio: 0.1, structure: "EMA_BULLISH", market_regime: "TREND", signal_authority: false }],
    currency_strength: [{ currency: "EUR", return_score_percent: 0.25, pair_count: 1 }], correlations: [], reason_codes: [],
  } }));
  await page.goto("/?view=research");
  const scanner = page.getByRole("region", { name: "Comparative market scanner" });
  await expect(scanner.getByText("EURUSD.x", { exact: true })).toBeVisible();
  await expect(scanner.getByText("Context ranking", { exact: false })).toBeVisible();
  await page.route("**/api/market/scan", (route) => route.fulfill({ status: 503, json: { detail: "Source unavailable" } }));
  await scanner.getByRole("button", { name: "Refresh scan" }).click();
  await expect(scanner.getByRole("alert")).toContainText("Source unavailable");
  await expect(scanner.getByRole("table")).toHaveCount(0);
});

test("top-down confirmation exposes a daily conflict without calling M1 approval", async ({ page }) => {
  const watch = { ...liveWatch, top_down: {
    version: "top-down-v1", state: "REJECTED", direction: "LONG_CONTEXT", observed_at_utc: observed, timeframes: [],
    stages: [
      { stage: "BIAS", state: "REJECTED", required: true, timeframes: ["D1", "H4"], evidence_timestamps: { D1: observed, H4: observed }, invalidation_price: null, reason_codes: ["DIRECTION_CONFLICT"] },
      { stage: "TIMING", state: "CONFIRMED", required: false, timeframes: ["M1"], evidence_timestamps: { M1: observed }, invalidation_price: null, reason_codes: ["OPTIONAL_TIMING_CANNOT_OVERRIDE_HIGHER_TIMEFRAMES"] },
    ],
  } };
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch, liveWatch: watch });
  await page.goto("/");
  await page.getByRole("group", { name: "Detailed research review" }).locator("summary").first().click();
  const panel = page.locator(".top-down-panel");
  await panel.locator("summary").click();
  await expect(panel.getByText("D1 / H4", { exact: true })).toBeVisible();
  await expect(panel.getByText("direction conflict", { exact: true })).toBeVisible();
  await expect(panel.getByText("M1 cannot replace higher-timeframe confirmation.", { exact: false })).toBeVisible();
});

test("live updates ignore quote and bar packets for another symbol", async ({ page }) => {
  let stream: import("@playwright/test").WebSocketRoute | undefined;
  await page.routeWebSocket("**/ws/live", (socket) => { stream = socket; });
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.goto("/");
  await expect(page.locator(".quotes")).toContainText("4077.75");
  stream!.send(JSON.stringify({ type: "quote", sequence: 100, observed_at_utc: new Date().toISOString(), payload: { ...liveQuote, symbol: "EURUSD", bid: 1.12, ask: 1.13, observed_at_utc: new Date().toISOString() } }));
  await expect(page.locator(".quotes")).not.toContainText("1.12");
  await expect(page.locator(".quotes")).toContainText("4077.75");
});

test("initial and periodic research refreshes share one in-flight request", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  let requests = 0;
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/research", async (route) => {
    requests++;
    await pending;
    await route.fulfill({ json: { ...liveResearch, live_research_watch: liveWatch } }).catch(() => {});
  });
  try {
    await page.goto("/");
    await expect.poll(() => requests).toBe(1);
    await page.waitForTimeout(5_500);
    expect(requests).toBe(1);
  } finally { release(); }
  await expect(page.locator(".live-research-watch")).toContainText("WITHHELD");
});

test("research and scanner automatically follow the active broker connection", async ({ page }) => {
  const timeline: object[] = [];
  page.on("response", async (response) => {
    const path = new URL(response.url()).pathname;
    if (path === "/api/connection" || path === "/api/research") {
      const body = await response.json().catch(() => null);
      timeline.push({ at: Date.now(), path, broker: body?.broker_server, symbol: body?.configured_symbol ?? body?.symbol, watch_symbol: body?.live_research_watch?.symbol, score: body?.live_research_watch?.evidence_score });
    }
  });
  await page.routeWebSocket("**/ws/live", () => {});
  const values = { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch, liveWatch };
  await mockSnapshot(page, values);
  let scans = 0;
  await page.route("**/api/market/scan", (route) => {
    scans++;
    return route.fulfill({ json: { data_status: "LIVE", observed_at_utc: new Date().toISOString(), instruments: [], currency_strength: [], correlations: [], reason_codes: [] } });
  });
  await page.goto("/?view=research");
  await expect(page.locator(".instrument")).toContainText("MetaQuotes-Demo");
  await expect.poll(() => scans).toBeGreaterThan(0);
  const initialScans = scans;
  values.connection = { ...liveConnection, broker_server: "Other-Demo", configured_symbol: "XAUUSD.a" };
  values.quote = { ...liveQuote, symbol: "XAUUSD.a", observed_at_utc: new Date().toISOString() };
  values.candles = { ...liveCandles, symbol: "XAUUSD.a" };
  values.research = { ...liveResearch, symbol: "XAUUSD.a" };
  values.liveWatch = { ...liveWatch, symbol: "XAUUSD.a", evidence_score: 63 };
  await expect(page.locator(".instrument")).toContainText("Other-Demo", { timeout: 10_000 });
  await expect.poll(() => scans, { timeout: 5_000 }).toBeGreaterThan(initialScans);
  try { await expect(page.locator(".live-research-watch")).toContainText("63/100"); }
  catch (cause) { console.log(JSON.stringify(timeline)); throw cause; }
});

test("top-down stages update through AJAX without closing the panel or reloading", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  let stage = "REJECTED";
  await page.route("**/api/research", (route) => route.fulfill({ json: { ...liveResearch, live_research_watch: { ...liveWatch, top_down: {
    version: "top-down-v1", state: stage, direction: "LONG_CONTEXT", observed_at_utc: new Date().toISOString(), timeframes: [], reason_codes: [],
    stages: [{ stage: "INTRADAY", required: true, state: stage, direction: "LONG_CONTEXT", timeframes: ["H1"], evidence_timestamps: { H1: observed }, reason_codes: [] }],
  } } } }));
  let navigations = 0;
  page.on("framenavigated", (frame) => { if (frame === page.mainFrame()) navigations++; });
  await page.goto("/");
  const review = page.getByRole("group", { name: "Detailed research review" });
  await review.locator("summary").first().click();
  const panel = page.locator(".top-down-panel");
  await panel.locator("summary").click();
  await expect(panel.locator("li b")).toHaveText("rejected");
  stage = "CONFIRMED";
  await expect(panel.locator("li b")).toHaveText("confirmed", { timeout: 9_000 });
  await expect(panel).toHaveAttribute("open", "");
  await expect(review).toHaveAttribute("open", "");
  expect(navigations).toBe(1);
});

test("a frozen top-down snapshot is labelled historical even with fresh quotes", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/research", (route) => route.fulfill({ json: { ...liveResearch, live_research_watch: { ...liveWatch, top_down: {
    version: "top-down-v1", state: "CONFIRMED", direction: "LONG_CONTEXT", observed_at_utc: observed, stages: [], timeframes: [], reason_codes: [],
  } } } }));
  await page.goto("/");
  await page.getByRole("group", { name: "Detailed research review" }).locator("summary").first().click();
  await page.locator(".top-down-panel summary").click();
  await expect(page.locator(".live-watch-pulse")).toHaveText("VERIFY SOURCE");
  await expect(page.locator(".top-down-panel")).toContainText("Last review only");
});

test("a slow chart request cannot swallow a newer timeframe selection", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  let h1Started = false;
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/candles**", async (route) => {
    const frame = new URL(route.request().url()).searchParams.get("tf");
    if (frame === "H1") { h1Started = true; await pending; }
    const candles = frame === "M15" ? [
      { ...liveCandles.candles[0], open_time_utc: "2026-10-22T10:15:00Z", completed: true },
      { ...liveCandles.candles[0], open_time_utc: "2026-10-22T10:30:00Z", completed: true },
      { ...liveCandles.candles[0], open_time_utc: "2026-10-22T10:45:00Z" },
    ] : liveCandles.candles;
    await route.fulfill({ json: { ...liveCandles, timeframe: frame, candles } }).catch(() => {});
  });
  try {
    await page.goto("/");
    await expect(page.locator(".chart-footer")).toContainText("Completed candles: 0");
    await page.getByRole("navigation", { name: "Chart timeframe" }).getByRole("button", { name: "H1", exact: true }).click();
    await expect.poll(() => h1Started).toBe(true);
    await page.getByRole("navigation", { name: "Chart timeframe" }).getByRole("button", { name: "M15", exact: true }).click();
    await expect(page.locator(".chart-footer")).toContainText("Completed candles: 2", { timeout: 4_000 });
    release();
    await expect(page.getByRole("button", { name: "M15", exact: true })).toHaveClass("selected");
    await expect(page.locator(".chart-footer")).toContainText("Completed candles: 2");
  } finally { release(); }
});

test("an open but silent stream recovers quotes through AJAX without a reload", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  let bid = 4077.75;
  await page.route("**/api/quote", (route) => route.fulfill({ json: { ...liveQuote, bid, ask: bid + 0.4, observed_at_utc: new Date().toISOString() } }));
  await page.goto("/");
  await expect(page.locator(".quotes")).toContainText("4077.75");
  await page.waitForTimeout(1_500); // Let the initial/open-handshake snapshots finish first.
  bid = 4080.5;
  await expect(page.locator(".quotes")).toContainText("4080.50", { timeout: 12_000 });
});

test("calendar and recorded observations stay live alongside the research panel", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  let updated = false;
  await page.route("**/api/events?scope=today", (route) => route.fulfill({ json: { ...events, events: updated ? [{ title: "Updated USD schedule", currency: "USD", impact: "High", event_time_utc: observed, event_time_manila: "2026-10-22T19:00:00+08:00", forecast: null, previous: null, actual: null, source: events.source, source_url: events.source_url }] : [] } }));
  await page.route("**/api/signals", (route) => route.fulfill({ json: { ...journal, evaluations: updated ? [{
    id: 2, evaluation_at_utc: observed, symbol: "XAUUSD", timeframe: "M5", candle_open_utc: observed,
    quote_source_timestamp_utc: observed, quote_bid: 4077.75, quote_ask: 4078.15, quote_status: "LIVE",
    market_state: "NO TRADE", evaluation_type: "DATA_OBSERVATION", strategy_version: "phase1-data-only-v1", reason_codes: ["NO_ORDER_EXECUTION"],
  }] : [] } }));
  await page.goto("/");
  await expect(page.locator(".today-events-card h2")).toHaveText("LIVE");
  await page.waitForTimeout(1_000);
  updated = true;
  await expect(page.locator(".today-events-card")).toContainText("Updated USD schedule", { timeout: 8_000 });
  await expect(page.locator(".journal-card")).toContainText("M5 CANDLE RECORDED");
});

test("a connection change retries immediately after discarding an in-flight old review", async ({ page }) => {
  let stream: import("@playwright/test").WebSocketRoute | undefined;
  await page.routeWebSocket("**/ws/live", (socket) => { stream = socket; });
  const values = { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch, liveWatch };
  await mockSnapshot(page, values);
  let first = true, started = false;
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/research", async (route) => {
    const body = { ...values.research, live_research_watch: values.liveWatch };
    if (first) { first = false; started = true; await pending; }
    await route.fulfill({ json: body }).catch(() => {});
  });
  try {
    await page.goto("/");
    await expect.poll(() => started).toBe(true);
    values.connection = { ...liveConnection, broker_server: "Other-Demo", configured_symbol: "XAUUSD.a" };
    values.quote = { ...liveQuote, symbol: "XAUUSD.a", observed_at_utc: new Date().toISOString() };
    values.candles = { ...liveCandles, symbol: "XAUUSD.a" };
    values.research = { ...liveResearch, symbol: "XAUUSD.a" };
    values.liveWatch = { ...liveWatch, symbol: "XAUUSD.a", evidence_score: 63 };
    stream!.send(JSON.stringify({ type: "provider_status", sequence: 100, observed_at_utc: new Date().toISOString(), payload: { data_status: "SOURCE_ERROR", reason_codes: ["SESSION_CHANGED"] } }));
    await expect(page.locator(".instrument")).toContainText("Other-Demo");
    release();
    await expect(page.locator(".live-research-watch")).toContainText("63/100", { timeout: 2_500 });
  } finally { release(); }
});

test("clearly blocks market analysis when MT5 is disconnected", async ({ page }, testInfo) => {
  await mockSnapshot(page, { connection: disconnected, quote: unavailableQuote, analysis: unavailableAnalysis, candles: unavailableCandles, research: unavailableResearch, liveWatch: unavailableLiveWatch });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Connect the terminal already signed in to your broker." })).toBeVisible();
  await expect(page.getByText("If you close MT5 later, PyonTrading disconnects and does not relaunch it.")).toBeVisible();
  await expect(page.getByText("No broker candles available")).toBeVisible();
  await expect(page.getByText("No price has been substituted.")).toHaveCount(0);
  await expect(page.getByLabel("Automatic live research watch")).toBeVisible();
  await expect(page.getByRole("heading", { name: "UNAVAILABLE" })).toBeVisible();
  await expect(page.getByLabel("Automatic live research watch").getByText("Research only · no order execution")).toBeVisible();
  await page.getByRole("group", { name: "Detailed research review" }).locator("summary").first().click();
  await expect(page.getByText("What changes this", { exact: true })).toBeVisible();
  await expect(page.getByText("Broker quote: NOT_CONFIGURED")).toBeVisible();
  await capturePhaseZeroBaseline(page, testInfo.project.name, "disconnected-market-desk");
});

test("research automation controller pauses and resumes the background worker", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/hfm/account/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_ACCOUNT", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: ["HFM_BROKER_NOT_VERIFIED"], connected: false,
    account_mode: "DEMO", broker_server: "MetaQuotes-Demo", account_id_suffix: null, configured_symbol: "XAUUSD",
  } }));
  let enabled = true;
  let statusRequests = 0;
  await page.route("**/api/research/pipeline", (route) => {
    statusRequests += 1;
    return route.fulfill({ json: { state: enabled ? "RUNNING" : "PAUSED", enabled, last_cycle_at_utc: observed, last_error: null, symbol: "XAUUSD" } });
  });
  await page.route("**/api/research/pipeline/control", async (route) => {
    if (route.request().headers()["x-pyon-operator-token"] !== "owner-token") {
      await route.fulfill({ status: 403, json: { detail: { reason_codes: ["OPERATOR_TOKEN_REQUIRED"] } } });
      return;
    }
    enabled = Boolean(JSON.parse(route.request().postData() ?? "{}").enabled);
    await route.fulfill({ json: { state: enabled ? "RUNNING" : "PAUSED", enabled, last_cycle_at_utc: observed, last_error: null, symbol: "XAUUSD" } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Automation" }).click();
  const controller = page.getByLabel("Research automation controller");
  await expect(controller).toContainText("Research running");
  await controller.getByRole("button", { name: "Pause research" }).click();
  await expect(controller.getByRole("alert")).toContainText("OPERATOR_TOKEN_REQUIRED");
  await expect.poll(() => statusRequests, { timeout: 8_000 }).toBeGreaterThan(1);
  await expect(controller.getByRole("alert")).toContainText("OPERATOR_TOKEN_REQUIRED");
  await expect(controller).toContainText("Research running");
  await controller.getByLabel("Local operator token").fill("owner-token");
  await controller.getByRole("button", { name: "Pause research" }).click();
  await expect(controller).toContainText("Research paused");
  await controller.getByRole("button", { name: "Resume research" }).click();
  await expect(controller).toContainText("Research running");
  await expect(page.getByText("Broker order automation is unavailable in this version.")).toBeVisible();
  await expect(page.getByText("Not verified", { exact: true })).toBeVisible();
});

test("research health separates a live quote from lagging completed-bar decisions", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/quote", (route) => route.fulfill({ json: { ...liveQuote, observed_at_utc: new Date().toISOString() } }));
  await page.route("**/api/research/pipeline", (route) => route.fulfill({ json: {
    state: "RUNNING", enabled: true, symbol: "XAUUSD", last_cycle_at_utc: new Date().toISOString(),
    last_error: null, last_market_data_status: "LIVE",
    coverage: {
      state: "BAR_LAGGING", worker_health: "ERROR", publication_state: "BLOCKED", broker_server: "MetaQuotes-Demo",
      identity_scope: "SYMBOL_ONLY_LEGACY_RUNS", latest_completed_m5_open_utc: "2026-10-22T10:55:00+00:00",
      latest_decision_m5_open_utc: "2026-10-22T10:45:00+00:00",
      unprocessed_archived_bars: 2, first_unprocessed_m5_open_utc: "2026-10-22T10:50:00+00:00",
    },
  } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Automation" }).click();
  const health = page.getByLabel("Research coverage");
  await expect(health).toContainText("Quote live");
  await expect(health).toContainText("Worker error");
  await expect(health).toContainText("Research stale");
  await expect(health).toContainText("Publication blocked");
  await expect(health).toContainText("2 archived bars without decisions");
});

test("closed market does not present an old research snapshot as a live quote or future review", async ({ page }) => {
  await mockSnapshot(page, {
    connection: liveConnection,
    quote: { ...liveQuote, data_status: "MARKET_CLOSED", observed_at_utc: new Date().toISOString(), tick_age_seconds: null, bid: null, ask: null },
    analysis: liveAnalysis, candles: liveCandles, research: liveResearch,
    liveWatch: { ...liveWatch, lifecycle: "EXPIRED", data_quality: { ...liveResearch.data_quality, status: "BLOCK", quote_status: "LIVE" } },
  });
  await page.route("**/api/research/pipeline", (route) => route.fulfill({ json: {
    state: "RUNNING", enabled: true, symbol: "XAUUSD", last_cycle_at_utc: new Date().toISOString(),
    last_error: null, last_market_data_status: "MARKET_CLOSED",
    coverage: {
      state: "SOURCE_UNAVAILABLE", worker_health: "RUNNING", publication_state: "BLOCKED",
      broker_server: "MetaQuotes-Demo", identity_scope: "SYMBOL_ONLY_LEGACY_RUNS",
      latest_completed_m5_open_utc: observed, latest_decision_m5_open_utc: observed,
      unprocessed_archived_bars: 0, first_unprocessed_m5_open_utc: null,
    },
  } }));

  await page.goto("/");
  await expect(page.locator(".source-chip")).toContainText("MARKET CLOSED");
  await expect(page.locator(".chart-footer .forming")).toContainText("LAST M5 BAR");
  const watch = page.getByLabel("Automatic live research watch");
  await expect(watch.locator(".live-watch-metrics article").filter({ hasText: "Data quality" })).toContainText("BLOCK");
  await expect(page.locator(".status-block")).toContainText("MARKET_CLOSED");
  await watch.getByRole("group", { name: "Detailed research review" }).locator("summary").first().click();
  await expect(watch.locator(".watch-bot-line")).toContainText("Quote MARKET CLOSED");
  await expect(watch.locator(".live-watch-metrics article").filter({ hasText: "Next review" })).toContainText("Awaiting market");
  await page.getByRole("button", { name: "Automation" }).click();
  await expect(page.getByLabel("Research coverage")).toContainText("Awaiting market");
});

test("validation explains withheld automatic signals from frozen proof checks", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/research/validation", (route) => route.fulfill({ json: {
    ...validation,
    labelled_candidates: 27,
    walk_forward: { training_labels: 16, validation_labels: 5, held_out_labels: 6, held_out_directional_matches: 1 },
    proof_audit: {
      source: "LOCAL_FROZEN_RESEARCH_RUNS", sample_limit: 500, sampled_runs: 50,
      proof_evaluated_runs: 41, eligible_runs: 0, published_signals: 0,
      latest_proof_anchor_utc: observed,
      failed_checks: [{ code: "COMPLETED_MTF_ALIGNMENT", runs: 41 }, { code: "CALENDAR_RISK_CHECKED", runs: 24 }],
      reason_codes: ["SYMBOL_ONLY_LEGACY_RUNS", "NOT_PERFORMANCE_VALIDATION", "NO_ELIGIBLE_PROOFS_IN_SAMPLE"],
    },
  } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Validation" }).click();
  const audit = page.getByLabel("Signal proof audit");
  await expect(audit).toContainText("41 proof-checked runs");
  await expect(audit).toContainText("0 automatically published");
  await expect(audit).toContainText("Completed MTF alignment");
  await expect(audit).toContainText("1 of 6 held-out directional matches");
  await expect(audit).toContainText("Not a performance validation");
});

test("full archive validation keeps chronological results separate from profit claims", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/backtests/validate", (route) => route.fulfill({ json: {
    api_version: "v1", source: "PYONTRADING2_FULL_ARCHIVE_WALK_FORWARD",
    observed_at_utc: observed, source_timestamp_utc: observed, data_status: "MARKET_CLOSED",
    reason_codes: ["CHRONOLOGICAL_60_20_20_SPLIT", "COMMISSION_UNAVAILABLE", "NO_MODEL_PROMOTION"],
    symbol: "XAUUSD", broker_server: "MetaQuotes-Demo", timeframe: "M5",
    dataset_start_utc: "2026-05-17T23:35:00Z", dataset_end_utc: observed, completed_candles: 31509, cache_hit: true,
    results: [{
      strategy_id: "M5_TREND_PULLBACK", strategy_version: "m5-trend-pullback-v1", selected_hold_bars: 3,
      training: { trials: 1000, wins: 550, losses: 450, gross_points: 2000, net_points: 1000 },
      validation: { trials: 367, wins: 180, losses: 187, gross_points: 200, net_points: -1255 },
      held_out: { trials: 368, wins: 200, losses: 168, gross_points: 15000, net_points: 13847 },
      state: "REVIEW_REQUIRED", reason_codes: ["COMMISSION_UNAVAILABLE", "NO_MODEL_PROMOTION"],
    }],
    limitation: "Standalone M5 strategy calibration only; recorded spread is not complete cost or live-signal profitability. No model promotion or order execution.",
  } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Validation" }).click();
  await page.getByRole("button", { name: "Validate full archive" }).click();
  const panel = page.getByLabel("Full archive hold-out validation");
  await expect(panel).toContainText("31,509 completed M5 bars");
  await expect(panel).toContainText("Reused unchanged archive result");
  const row = panel.getByRole("row", { name: /M5 trend pullback/i });
  await expect(row).toContainText("−1,255");
  await expect(row).toContainText("+13,847");
  await expect(panel).toContainText("not net profit");
});

test("shows only token-protected, verified HFM USD funds and clears them when unavailable", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  let verified = true;
  await page.route("**/api/hfm/account/financials", (route) => {
    if (route.request().headers()["x-pyon-operator-token"] !== "owner-token") {
      return route.fulfill({ status: 403, json: { detail: { reason_codes: ["OPERATOR_TOKEN_REQUIRED"] } } });
    }
    return route.fulfill({ json: {
      api_version: "v1", source: "MT5_HFM_ACCOUNT", source_timestamp_utc: null, observed_at_utc: new Date().toISOString(),
      data_status: verified ? "LIVE" : "SOURCE_ERROR", reason_codes: verified ? [] : ["HFM_BROKER_NOT_VERIFIED"],
      account_mode: verified ? "DEMO" : "UNKNOWN", broker_server: verified ? "HFMarketsGlobal-Demo" : null,
      account_id_suffix: verified ? "5678" : null, currency: verified ? "USD" : null,
      balance: verified ? 10000.25 : null, equity: verified ? 10012.5 : null,
    } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Automation" }).click();
  const funds = page.getByLabel("HFM account funds");
  await expect(funds).toContainText("Enter operator token");
  await expect(funds).not.toContainText("10,000.25");
  await page.getByLabel("Research automation controller").getByLabel("Local operator token").fill("owner-token");
  await expect(funds).toContainText(/USD\s*10,000\.25/);
  await expect(funds).toContainText(/USD\s*10,012\.50/);
  verified = false;
  await expect(funds).toContainText("HFM_BROKER_NOT_VERIFIED", { timeout: 8_000 });
  await expect(funds).not.toContainText("10,000.25");
});

test("stopped research worker cannot be falsely resumed by a toggle", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/research/pipeline", (route) => route.fulfill({ json: { state: "STOPPED", enabled: true, last_cycle_at_utc: null, last_error: "WORKER_FAILED", symbol: "XAUUSD" } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Automation" }).click();
  const controller = page.getByLabel("Research automation controller");
  await expect(controller).toContainText("Worker stopped");
  await expect(controller.getByRole("button", { name: "Restart app to recover worker" })).toBeDisabled();
});

test("automation cost status remains readable at a 1024px viewport", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/research/pipeline", (route) => route.fulfill({ json: { state: "RUNNING", enabled: true, last_cycle_at_utc: observed, last_error: null, symbol: "XAUUSD" } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Automation" }).click();
  const costs = page.getByText("COSTS INCOMPLETE", { exact: true });
  await expect(costs).toBeVisible();
  expect(await costs.evaluate((element) => element.getBoundingClientRect().height)).toBeLessThanOrEqual(36);
});

test("keeps critical market data visible when the calendar refresh fails", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/events?scope=today", (route) => route.fulfill({ status: 503, json: { detail: "CALENDAR_UPSTREAM_UNAVAILABLE" } }));

  await page.goto("/");

  await expect(page.getByText("4077.75", { exact: true })).toBeVisible();
  await expect(page.getByText("M5 broker-candle data · 0 completed · 1 forming")).toBeVisible();
  await expect(page.getByText("Calendar refresh issue: CALENDAR_UPSTREAM_UNAVAILABLE")).toBeVisible();
  await expect(page.getByText("Unable to refresh broker data", { exact: false })).toHaveCount(0);
});

test("keeps broker data visible and identifies a research refresh failure", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/research", (route) => route.fulfill({ status: 503, json: { detail: "RESEARCH_COORDINATOR_UNAVAILABLE" } }));

  await page.goto("/");

  await expect(page.getByText("4077.75", { exact: true })).toBeVisible();
  await expect(page.getByText("Research refresh issue: RESEARCH_COORDINATOR_UNAVAILABLE")).toBeVisible();
  await expect(page.getByText("Unable to refresh broker data", { exact: false })).toHaveCount(0);
});

test("renders live research bots and a no-execution market review", async ({ page }, testInfo) => {
  // This end-to-end flow visits every workspace and opens/minimizes/restores a modal.
  test.setTimeout(60_000);
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  // This scenario tests a continuously live source, not the separate stale-quote behavior.
  await page.route("**/api/quote", (route) => route.fulfill({ json: { ...liveQuote, observed_at_utc: new Date().toISOString() } }));
  await page.route("**/api/research/analyze", (route) => route.fulfill({ json: marketReview }));

  await page.goto("/");

  await capturePhaseZeroBaseline(page, testInfo.project.name, "market-desk");

  await expect(page.getByText("M5 broker-candle data · 0 completed · 1 forming")).toBeVisible();
  await expect(page.getByText("FORMING M5 · 10:55:00 UTC")).toBeVisible();

  await expect(page.getByLabel("Automatic live research watch")).toBeVisible();
  await expect(page.getByText("WITHHELD", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Automatic live research watch").getByText("No entry / stop / targets", { exact: true })).toBeVisible();
  await expect(page.getByText("USD event risk", { exact: true })).toBeVisible();
  await expect(page.locator(".watch-bot-line")).toContainText("coverage, not probability");
  await expect(page.getByText("Data quality", { exact: true })).toBeVisible();
  await expect(page.getByText("Research horizon", { exact: true })).toBeVisible();
  await expect(page.getByText("Not established", { exact: true })).toBeVisible();
  await expect(page.locator(".watch-bot-line")).toContainText("Bots:");
  await expect(page.locator(".watch-bot-line")).toContainText("aligned");
  await expect(page.getByLabel("Automatic live research watch").getByText("Direction", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Automatic live research watch").getByText("Research boundary", { exact: true })).toHaveCount(0);
  await expect(page.getByText("DATA HEALTH", { exact: true })).toHaveCount(0);
  await expect(page.locator(".chart-context-line")).not.toContainText("Research:");
  await expect(page.getByRole("button", { name: "Save review snapshot" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset chart view" })).toBeVisible();
  await page.getByRole("button", { name: "Reset chart view" }).click();
  await expect(page.getByText("View research network")).toBeVisible();
  await page.locator(".chart-options summary").click();
  await expect(page.getByRole("button", { name: "EMA 20 / 60" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Tick activity" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Bands 20,2" }).click();
  await expect(page.getByRole("button", { name: "Bands 20,2" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Chart overlays")).toContainText("BOLLINGER 20,2");

  await page.getByRole("button", { name: "Research network", exact: true }).click();
  await expect(page.getByText("Chart analyst")).toBeVisible();
  await expect(page.getByText("Data quality sentinel")).toBeVisible();
  await expect(page.getByText("Macro & event watcher")).toBeVisible();
  await expect(page.getByText("Strategy ensemble & abstention")).toBeVisible();
  await capturePhaseZeroBaseline(page, testInfo.project.name, "research-network");

  if (testInfo.project.name === "mobile-chrome") {
    await page.getByRole("button", { name: "Save review snapshot" }).click();
    await expect(page.getByRole("dialog").getByRole("heading", { name: "NO TRADE" })).toBeVisible();
    await capturePhaseZeroBaseline(page, testInfo.project.name, "market-review-modal");
    await page.getByRole("button", { name: "Close" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Sources & rules" }).click();
    await expect(page.getByText("Verify research sources")).toBeVisible();
    await capturePhaseZeroBaseline(page, testInfo.project.name, "sources-rules");
    await page.getByRole("button", { name: "History" }).click();
    await expect(page.getByRole("heading", { name: "History", exact: true })).toBeVisible();
    await expect(page.getByText("On-demand research reviews (1)")).toBeVisible();
    await capturePhaseZeroBaseline(page, testInfo.project.name, "history");
    await page.getByRole("button", { name: "Validation" }).click();
    await capturePhaseZeroBaseline(page, testInfo.project.name, "validation");
    await expect(page.getByText("Historical M5 research")).toBeVisible();
    return;
  }

  await page.getByRole("button", { name: "Sources & rules" }).click();
  await expect(page.getByText("Verify research sources")).toBeVisible();
  await expect(page.getByText("Local rule enablement")).toBeVisible();
  await page.getByRole("button", { name: "Check sources" }).click();
  await expect(page.getByText("Licensed futures order flow")).toBeVisible();
  await expect(page.getByText("NO PROVIDER CONFIGURED")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Configure exact MT5 context symbols" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Disable" }).first()).toBeVisible();
  await page.getByLabel("Volatility index or proxy").fill("VIXY");
  await page.getByRole("button", { name: "Save context" }).click();
  await expect(page.getByLabel("Volatility index or proxy")).toHaveValue("VIXY");
  await capturePhaseZeroBaseline(page, testInfo.project.name, "sources-rules");

  await page.getByRole("button", { name: "History" }).click();
  await expect(page.getByText("No automatic signals yet")).toBeVisible();
  await page.getByText("On-demand research reviews (1)").click();
  await expect(page.getByText("History keeps this source-labelled research result.")).toBeVisible();
  await capturePhaseZeroBaseline(page, testInfo.project.name, "history");

  await page.getByRole("button", { name: "Research network", exact: true }).click();
  await page.getByRole("button", { name: "Save review snapshot" }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "NO TRADE" })).toBeVisible();
  await expect(page.getByText("M5 technical readings")).toBeVisible();
  await expect(page.getByText("Integrity & regime")).toBeVisible();
  await expect(page.getByText("Professional research modules")).toBeVisible();
  await expect(page.getByText("Estimated CVD")).toBeVisible();
  await expect(page.getByText("Deterministic rule ensemble")).toBeVisible();
  await expect(page.getByText("4078.30 / 4085.61")).toBeVisible();
  await expect(page.getByLabel("Multi-timeframe broker-candle evidence")).toContainText("M5");
  await expect(page.getByText("NO ORDER EXECUTION", { exact: false }).last()).toBeVisible();
  await capturePhaseZeroBaseline(page, testInfo.project.name, "market-review-modal");
  await page.getByRole("button", { name: "Minimize" }).click();
  await expect(page.getByRole("complementary", { name: "Minimized market analysis" })).toBeVisible();
  await page.getByRole("button", { name: "Open" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Validation" }).click();
  await capturePhaseZeroBaseline(page, testInfo.project.name, "validation");
  await expect(page.getByText("Historical M5 research")).toBeVisible();
});

test("labels ready source capabilities without an unavailable data category", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });

  await page.goto("/");
  await page.getByRole("button", { name: "Sources & rules" }).click();
  await page.getByRole("button", { name: "Check sources" }).click();

  const terminalCapability = page.locator(".source-capability-list li").filter({ hasText: "MT5 terminal" });
  const candleCapability = page.locator(".source-capability-list li").filter({ hasText: "Broker candles" });
  const tickCapability = page.locator(".source-capability-list li").filter({ hasText: "Broker tick activity" });
  await expect(terminalCapability).toContainText("LOCAL META TRADER 5");
  await expect(terminalCapability).not.toContainText("UNAVAILABLE");
  await expect(candleCapability).not.toContainText("UNAVAILABLE");
  await expect(tickCapability).toContainText("BROKER TICK PROXY");
});

test("shows optional demo binding separately from a connected HFM demo account", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/hfm/account/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_ACCOUNT", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: [], connected: true,
    account_mode: "DEMO", broker_server: "HFMarketsGlobal-Demo", configured_symbol: "XAUUSD",
  } }));
  await page.route("**/api/hfm/demo/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_DEMO", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: ["DEMO_ACCOUNT_BINDING_NOT_CONFIGURED"], ready: false,
    account_mode: "DEMO", broker_server: "HFMarketsGlobal-Demo", configured_symbol: "XAUUSD",
  } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Sources & rules" }).click();

  const demoCard = page.getByLabel("HFM account connection");
  await expect(demoCard).toContainText("HFM DEMO CONNECTED");
  await expect(demoCard).toContainText("Optional demo safety binding: not verified");
  await expect(demoCard).toContainText("Set PYON_HFM_DEMO_LOGIN");
});

test("automatically detects an HFM sign-in while Sources & rules stays open", async ({ page }) => {
  await page.clock.install();
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  let checks = 0;
  await page.route("**/api/hfm/account/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_ACCOUNT", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: checks++ === 0 ? "SOURCE_ERROR" : "LIVE",
    reason_codes: checks === 1 ? ["HFM_BROKER_NOT_VERIFIED"] : [],
    connected: checks > 1, account_mode: "DEMO",
    broker_server: checks === 1 ? "MetaQuotes-Demo" : "HFMarketsGlobal-Demo",
    configured_symbol: "XAUUSD",
  } }));
  await page.route("**/api/hfm/demo/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_DEMO", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: ["DEMO_ACCOUNT_BINDING_NOT_CONFIGURED"], ready: false,
    account_mode: "DEMO", broker_server: "HFMarketsGlobal-Demo", configured_symbol: "XAUUSD",
  } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Sources & rules" }).click();
  const card = page.getByLabel("HFM account connection");
  await expect(card).toContainText("not verified as HFM");
  await page.clock.fastForward(10_000);
  await expect(card).toContainText("HFM DEMO CONNECTED");
  await expect(card).toContainText("HFMarketsGlobal-Demo");
});

test("shows a real HFM account without an irrelevant demo readiness warning", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/hfm/account/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_ACCOUNT", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: [], connected: true,
    account_mode: "LIVE", broker_server: "HFMarketsGlobal-Live1", configured_symbol: "XAUUSD",
  } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Sources & rules" }).click();
  const card = page.getByLabel("HFM account connection");
  await expect(card).toContainText("HFM LIVE CONNECTED");
  await expect(card).not.toContainText("Demo trading readiness");
});

test("lets the user choose a target account type and identifies a mismatch with active MT5", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/hfm/account/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_ACCOUNT", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: [], connected: true,
    account_mode: "DEMO", broker_server: "HFMarketsGlobal-Demo", account_id_suffix: "5678", configured_symbol: "XAUUSD",
  } }));
  await page.route("**/api/hfm/demo/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_DEMO", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: ["DEMO_ACCOUNT_BINDING_NOT_CONFIGURED"], ready: false,
    account_mode: "DEMO", broker_server: "HFMarketsGlobal-Demo", configured_symbol: "XAUUSD",
  } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Sources & rules" }).click();
  const card = page.getByLabel("HFM account connection");
  await expect(card).toContainText("Account ending 5678");
  await card.getByRole("combobox", { name: "Account type to use" }).selectOption("LIVE");
  await expect(card).toContainText("Selected real account is not active in MT5");
  await card.getByRole("combobox", { name: "Account type to use" }).selectOption("DEMO");
  await expect(card).toContainText("Selected demo account is active in MT5");
});

test("shows a verified HFM real account as connected for research without taking credentials", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/hfm/account/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_ACCOUNT", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: [], connected: true,
    account_mode: "LIVE", broker_server: "HFMarketsGlobal-Live1", configured_symbol: "XAUUSD",
  } }));
  await page.route("**/api/hfm/demo/status", (route) => route.fulfill({ json: {
    api_version: "v1", source: "MT5_HFM_DEMO", source_timestamp_utc: null, observed_at_utc: observed,
    data_status: "LIVE", reason_codes: ["HFM_DEMO_ACCOUNT_REQUIRED"], ready: false,
    account_mode: "LIVE", broker_server: "HFMarketsGlobal-Live1", configured_symbol: "XAUUSD",
  } }));

  await page.goto("/");
  await page.getByRole("button", { name: "Sources & rules" }).click();
  await page.getByRole("button", { name: "Check HFM connection" }).click();

  const card = page.getByLabel("HFM account connection");
  await expect(card).toContainText("HFM LIVE CONNECTED");
  await expect(card).toContainText("Selected demo account is not active in MT5");
  await card.getByRole("combobox", { name: "Account type to use" }).selectOption("LIVE");
  await expect(card).toContainText("Selected real account is active in MT5");
  await expect(card).toContainText("Real-account order automation is locked");
  await expect(card).toContainText("HFMarketsGlobal-Live1");
  await expect(card).not.toContainText("Optional demo safety binding");
  await expect(card.getByRole("link", { name: "Open HFM account portal" })).toHaveAttribute("href", "https://my.hfm.com/en/login");
  await expect(card.locator('input[type="password"]')).toHaveCount(0);
});

test("first-run guidance accepts either HFM account type and directs sign-in to MT5", async ({ page }) => {
  await mockSnapshot(page, { connection: disconnected, quote: unavailableQuote, analysis: unavailableAnalysis, candles: unavailableCandles, research: unavailableResearch });

  await page.goto("/");

  const wizard = page.getByRole("heading", { name: "Connect the terminal already signed in to your broker." }).locator("..");
  await expect(wizard).toContainText("demo or real HFM MT5 trading account");
  await expect(wizard.getByRole("link", { name: "Open HFM account portal" })).toHaveAttribute("href", "https://my.hfm.com/en/login");
});

test("identifies observers that are not configured instead of calling them pending", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });

  await page.goto("/");

  const coordination = page.locator(".watch-bot-line");
  await expect(coordination).toContainText("5/6 live");
  await expect(coordination).toContainText("1 not configured");
  await expect(coordination).not.toContainText("1 pending");
});

test("distinguishes a data-only journal observation from a strategy result", async ({ page }) => {
  const dataOnlyJournal = {
    ...journal,
    evaluations: [{
      id: 1, evaluation_at_utc: observed, symbol: "XAUUSD", timeframe: "M5", candle_open_utc: observed,
      quote_source_timestamp_utc: observed, quote_bid: 4077.75, quote_ask: 4078.15, quote_status: "LIVE",
      market_state: "NO TRADE", evaluation_type: "DATA_OBSERVATION", strategy_version: "phase1-data-only-v1",
      reason_codes: ["PHASE_2_STRATEGY_NOT_IMPLEMENTED", "NO_ORDER_EXECUTION"],
    }],
  };
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/signals", (route) => route.fulfill({ json: dataOnlyJournal }));

  await page.goto("/");

  const latestObservation = page.locator(".journal-card");
  await expect(latestObservation).toContainText("M5 CANDLE RECORDED");
  await expect(latestObservation).toContainText("DATA OBSERVATION ONLY");
  await expect(latestObservation).not.toContainText("PHASE 2 STRATEGY NOT IMPLEMENTED");
});

test("keeps context-source fields named and visibly focused", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });

  await page.goto("/");
  await page.getByRole("button", { name: "Sources & rules" }).click();

  const dollarIndex = page.getByLabel("Dollar index");
  await expect(dollarIndex).toHaveAttribute("name", "dxy_symbol");
  await dollarIndex.focus();
  await expect(dollarIndex).toHaveCSS("outline-color", "rgb(231, 191, 83)");
});

test("shows an aligned research watch without turning it into an order instruction", async ({ page }, testInfo) => {
  const watchResearch = {
    ...liveResearch,
    market_state: "WATCH SHORT",
    data_quality: { ...liveResearch.data_quality, status: "WATCH", candle_gap_count: 1 },
    strategy_ensemble: { ...liveResearch.strategy_ensemble, decision: "WATCH_SHORT", agreement_count: 2, reason_codes: ["DATA_QUALITY_WATCH_NON_BLOCKING", "NO_ORDER_EXECUTION"] },
  };
  const watchAnalysis = {
    ...liveAnalysis,
    market_state: "WATCH SHORT",
    direction_context: "Watch-short research condition: completed-candle rules agree. This is not an order instruction.",
    execution_gate: [{ label: "Tick / candle integrity", state: "WATCH", reason: "WATCH" }],
  };
  const watchReview = {
    ...marketReview,
    decision: "WATCH_SHORT",
    summary: "Watch-short research condition: completed-candle rules agree. This is not an execution instruction.",
    gates: [{ label: "Tick / candle integrity", state: "WATCH", reason: "WATCH" }],
    data_quality: watchResearch.data_quality,
    strategy_ensemble: watchResearch.strategy_ensemble,
  };
  const activeWatch = {
    ...liveWatch,
    expires_at_utc: new Date(Date.now() + 5 * 60_000).toISOString(),
    lifecycle: "ACTIVE_RESEARCH_WATCH",
    direction: "SHORT_CONTEXT",
    evidence_score: 100,
    research_horizon: "MULTI_SESSION_CONTEXT",
    horizon_basis: "M5_M15_H1_H4_COMPLETED_CANDLES_ALIGNED",
    horizon_review_at_utc: "2026-10-22T04:00:00Z",
    horizon_reason_codes: ["M5_M15_H1_H4_COMPLETED_CANDLES_ALIGNED", "H4_CONTEXT_CONFIRMED"],
    summary: "Watch short is active as a completed-candle research watch until the next review. It is not a trade instruction, probability, or performance claim.",
    invalidation_conditions: ["A newer completed M5 candle triggers the next review.", "The watch is withdrawn if broker data becomes stale or rules disagree.", "The watch is withdrawn if verified USD-event risk becomes elevated."],
    strategy_ensemble: watchResearch.strategy_ensemble,
    reference_levels: { entry: 4077.75, stop_loss: 4082.62, take_profit_1: 4072.88, take_profit_2: 4068.01, source_candle_close_utc: observed, quote_observed_at_utc: observed, basis: "M5_ATR14_1R_2R_UNVALIDATED" },
    reference_levels_reason: "UNVALIDATED_REFERENCE_ONLY",
    signal_proof: { publication_state: "WITHHELD", performance_state: "UNVALIDATED", checks: [
      { code: "FRESH_BROKER_QUOTE", passed: true, detail: "Fresh broker quote" },
      { code: "DATA_QUALITY_CLEAR", passed: false, detail: "Spread baseline is incomplete" },
    ], rule_versions: ["structure-alignment-v1"], reason_codes: ["DATA_QUALITY_CLEAR", "PERFORMANCE_UNVALIDATED"] },
  };
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: watchAnalysis, candles: liveCandles, research: watchResearch, liveWatch: activeWatch });
  await page.route("**/api/quote", (route) => route.fulfill({ json: { ...liveQuote, observed_at_utc: new Date().toISOString() } }));
  await page.route("**/api/research/analyze", (route) => route.fulfill({ json: watchReview }));

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "WATCH SHORT" })).toBeVisible();
  await expect(page.locator(".watch-primary-blocker")).toContainText("Unmet requirement");
  await expect(page.locator(".watch-primary-blocker")).toContainText("Spread baseline is incomplete");
  const levels = page.getByLabel("Research reference levels");
  await expect(levels.getByText("Entry", { exact: true })).toBeVisible();
  await expect(levels.getByText("4,077.75", { exact: true })).toBeVisible();
  await expect(levels.getByText("Stop", { exact: true })).toBeVisible();
  await expect(levels.getByText("TP1", { exact: true })).toBeVisible();
  await expect(levels.getByText("TP2", { exact: true })).toBeVisible();
  await capturePhaseZeroBaseline(page, testInfo.project.name, "active-research-watch");
  const watchSummary = page.locator(".live-watch-summary");
  await expect(watchSummary).toContainText("Automatic monitoring is active and withdraws when a source or rule changes.");
  await expect(watchSummary).toBeVisible();
  await page.getByRole("group", { name: "Detailed research review" }).locator("summary").first().click();
  await expect(page.getByText("100/100")).toBeVisible();
  await expect(page.getByText("Multi-session context", { exact: true })).toBeVisible();
  await expect(page.getByText("M5 / M15 / H1 / H4 aligned", { exact: false })).toBeVisible();
  await expect(page.getByLabel("Signal publication proof")).toContainText("Signal publication withheld");
  await expect(page.getByLabel("Signal publication proof")).toContainText("1/2 checks passed");
  await expect(page.getByLabel("Signal publication proof")).toContainText("First blocker: DATA_QUALITY_CLEAR");
  await expect(page.getByLabel("Signal publication proof")).toContainText("Spread baseline is incomplete");
  await page.getByRole("button", { name: "Save review snapshot" }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "WATCH SHORT" })).toBeVisible();
  await expect(page.locator(".modal-gates .gate-watch")).toHaveText("WATCH");
  await expect(page.getByRole("dialog").getByText("No order execution", { exact: true })).toBeVisible();
});

test("a short context without confirmed risk is pending, then live levels appear after confirmation", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/quote", (route) => route.fulfill({ json: { ...liveQuote, observed_at_utc: new Date().toISOString() } }));
  let confirmed = false;
  let documents = 0;
  page.on("request", (request) => { if (request.resourceType() === "document") documents++; });
  await page.route("**/api/research", (route) => route.fulfill({ json: { ...liveResearch, live_research_watch: {
    ...liveWatch, observed_at_utc: new Date().toISOString(), lifecycle: "ACTIVE_RESEARCH_WATCH", direction: "SHORT_CONTEXT",
    expires_at_utc: new Date(Date.now() + 300_000).toISOString(),
    data_quality: { ...liveResearch.data_quality, status: confirmed ? "CLEAR" : "WATCH", candle_gap_count: confirmed ? 0 : 1 },
    reference_levels_reason: confirmed ? "UNVALIDATED_REFERENCE_ONLY" : "TOP_DOWN_CONFIRMATION_REQUIRED",
    reference_levels: confirmed ? { entry: 4077.75, stop_loss: 4082.62, take_profit_1: 4072.88, take_profit_2: 4068.01, source_candle_close_utc: observed, quote_observed_at_utc: new Date().toISOString(), basis: "M5_ATR14_1R_2R_UNVALIDATED" } : null,
    top_down: { version: "top-down-v1", state: confirmed ? "CONFIRMED" : "REJECTED", direction: "SHORT_CONTEXT", observed_at_utc: new Date().toISOString(), timeframes: [], reason_codes: [], stages: [
      { stage: "RISK", required: true, state: confirmed ? "CONFIRMED" : "REJECTED", timeframes: [], evidence_timestamps: {}, reason_codes: ["EXISTING_SOURCE_AND_RISK_GATES"] },
      { stage: "TIMING", required: false, state: "REJECTED", timeframes: ["M1"], evidence_timestamps: {}, reason_codes: ["OPTIONAL_TIMING_CANNOT_OVERRIDE_HIGHER_TIMEFRAMES"] },
    ] },
    signal_proof: { publication_state: confirmed ? "ELIGIBLE" : "WITHHELD", performance_state: "UNVALIDATED", rule_versions: [], reason_codes: [], checks: [
      { code: "DATA_QUALITY_CLEAR", passed: confirmed, detail: "Integrity clear and spread within observed range" },
    ] },
  } } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "SHORT SETUP PENDING", exact: true })).toBeVisible();
  const levels = page.getByLabel("Research reference levels");
  await expect(levels).toContainText("Waiting for: Risk checks");
  await expect(levels.getByText("Entry", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Signal publication proof")).toContainText("1 gap in completed M5 candles");
  confirmed = true;
  await expect(page.getByRole("heading", { name: "WATCH SHORT", exact: true })).toBeVisible({ timeout: 9_000 });
  await expect(levels.getByText("4,077.75", { exact: true })).toBeVisible();
  await expect(levels.getByText("TP1", { exact: true })).toBeVisible();
  await expect(levels.getByText("TP2", { exact: true })).toBeVisible();
  expect(documents).toBe(1);
});

test("a long context with price outside the scenario range is not presented as an entry signal", async ({ page }) => {
  await page.routeWebSocket("**/ws/live", () => {});
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date().toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch, liveWatch: {
    ...liveWatch, lifecycle: "ACTIVE_RESEARCH_WATCH", direction: "LONG_CONTEXT", expires_at_utc: new Date(Date.now() + 300_000).toISOString(),
    reference_levels: null, reference_levels_reason: "QUOTE_OUTSIDE_COMPLETED_M5_ATR",
  } });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "LONG SETUP PENDING", exact: true })).toBeVisible();
  await expect(page.getByLabel("Research reference levels")).toContainText("Price moved beyond the last completed M5 ATR");
  await expect(page.getByLabel("Research reference levels").getByText("Entry", { exact: true })).toHaveCount(0);
});

test("hides an old reference setup when the broker quote becomes stale", async ({ page }) => {
  const unsafeWatch = {
    ...liveWatch,
    lifecycle: "ACTIVE_RESEARCH_WATCH",
    direction: "SHORT_CONTEXT",
    reference_levels: { entry: 4077.75, stop_loss: 4082.62, take_profit_1: 4072.88, take_profit_2: 4068.01, source_candle_close_utc: observed, quote_observed_at_utc: observed, basis: "M5_ATR14_1R_2R_UNVALIDATED" },
  };
  await mockSnapshot(page, {
    connection: liveConnection,
    quote: { ...liveQuote, data_status: "STALE", tick_age_seconds: 12 },
    analysis: liveAnalysis, candles: liveCandles, research: liveResearch, liveWatch: unsafeWatch,
  });
  await page.goto("/");
  const levels = page.getByLabel("Research reference levels");
  await expect(levels.getByText("No entry / stop / targets", { exact: true })).toBeVisible();
  await expect(levels.getByText("4,077.75", { exact: true })).toHaveCount(0);
});

test("keeps a workspace view addressable and restores it with browser back", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.goto("/?view=history");
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  await page.getByRole("button", { name: "Research network", exact: true }).click();
  await expect(page).toHaveURL(/view=research/);
  await page.goBack();
  await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
});

test("alerts on a new qualified signal and shows its frozen levels and proof in history", async ({ page }) => {
  const now = Date.now();
  let entries: object[] = [];
  let quoteState: "LIVE" | "STALE" = "LIVE";
  await mockSnapshot(page, { connection: liveConnection, quote: { ...liveQuote, observed_at_utc: new Date(now).toISOString() }, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/quote", (route) => route.fulfill({ json: {
    ...liveQuote, data_status: quoteState, observed_at_utc: new Date().toISOString(), tick_age_seconds: quoteState === "LIVE" ? 0.2 : 12,
  } }));
  await page.route("**/api/signals/history", (route) => route.fulfill({ json: { ...signalHistory, entries } }));
  await page.goto("/");
  await page.getByRole("button", { name: "History" }).click();
  await expect(page.getByText("No automatic signals yet")).toBeVisible();

  entries = [{
    signal_id: "auto-qualified-1", provided_at_utc: new Date(now).toISOString(), symbol: "XAUUSD",
    source: "PYONTRADING2_LIVE_RESEARCH_WATCH", source_timestamp_utc: new Date(now - 300_000).toISOString(),
    data_status: "LIVE", analysis_mode: "AUTOMATIC_RESEARCH_WATCH_V1", signal_kind: "AUTOMATIC",
    broker_server: "MetaQuotes-Demo", feature_set_version: "mtf-research-v4",
    decision: "WATCH_LONG", market_context: "UPWARD_STRUCTURE", summary: "Qualified completed-candle research watch.",
    event_risk_state: "NO_EVENT_IN_EXPORT", paper_status: "NOT_CREATED", input_fingerprint: "frozen-proof",
    reason_codes: ["PERFORMANCE_UNVALIDATED", "NO_ORDER_EXECUTION"],
    expires_at_utc: new Date(now + 300_000).toISOString(),
    reference_levels: { entry: 4078.15, stop_loss: 4073.15, take_profit_1: 4083.15, take_profit_2: 4088.15,
      source_candle_close_utc: new Date(now - 300_000).toISOString(), quote_observed_at_utc: new Date(now).toISOString(), basis: "M5_ATR14_1R_2R_UNVALIDATED" },
    signal_proof: { publication_state: "ELIGIBLE", performance_state: "UNVALIDATED", checks: [
      { code: "FRESH_BROKER_QUOTE", passed: true, detail: "Live quote" },
      { code: "COMPLETED_MTF_ALIGNMENT", passed: true, detail: "Completed candles" },
    ], rule_versions: ["structure-alignment-v1"], reason_codes: ["PERFORMANCE_UNVALIDATED"] },
  }];

  await expect(page.getByLabel("New research signal")).toContainText("WATCH LONG", { timeout: 12_000 });
  await expect(page.locator(".signal-history-card")).toContainText("4,078.15");
  await expect(page.locator(".signal-history-card")).toContainText("4,073.15");
  await expect(page.locator(".signal-history-card")).toContainText("4,083.15");
  await expect(page.locator(".signal-history-card")).toContainText("4,088.15");
  await expect(page.locator(".signal-history-card")).toContainText("2/2 source checks");
  await expect(page.locator(".signal-history-card")).toContainText("Unvalidated performance");
  await expect(page.locator(".signal-history-card")).toContainText("12-bar follow-up: awaiting completed candles");
  entries = [{ ...entries[0], forward_outcome: {
    signal_id: "auto-qualified-1", label_version: "m5-12-close-direction-v1", broker_server: "MetaQuotes-Demo",
    horizon_bars: 12, anchor_close_utc: new Date(now - 300_000).toISOString(),
    outcome_close_utc: new Date(now + 3_300_000).toISOString(),
    anchor_close: 4078.15, outcome_close: 4080.15, directional_change: 2,
    directional_state: "FAVORABLE", source: "MT5_COMPLETED_M5_CANDLES",
    labelled_at_utc: new Date(now + 3_300_000).toISOString(),
  } }];
  await expect(page.locator(".signal-history-card")).toContainText("12-bar follow-up: favorable", { timeout: 8_000 });
  await expect(page.locator(".signal-history-card")).toContainText("Not a fill or P&L");
  quoteState = "STALE";
  await expect(page.getByLabel("New research signal")).toHaveCount(0, { timeout: 8_000 });
});

test("withdraws last-known live prices and levels when quote packets stop", async ({ page }) => {
  const staleWatch = {
    ...liveWatch,
    lifecycle: "ACTIVE_RESEARCH_WATCH",
    direction: "SHORT_CONTEXT",
    expires_at_utc: new Date(Date.now() + 5 * 60_000).toISOString(),
    reference_levels: { entry: 4077.75, stop_loss: 4082.62, take_profit_1: 4072.88, take_profit_2: 4068.01, source_candle_close_utc: observed, quote_observed_at_utc: observed, basis: "M5_ATR14_1R_2R_UNVALIDATED" },
  };
  await mockSnapshot(page, {
    connection: liveConnection,
    quote: { ...liveQuote, observed_at_utc: new Date(Date.now() - 12_000).toISOString() },
    analysis: liveAnalysis, candles: liveCandles, research: liveResearch, liveWatch: staleWatch,
  });
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: "STALE" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "SOURCE STALE" })).toBeVisible();
  await expect(page.getByLabel("Research reference levels")).toContainText("No entry / stop / targets");
  await expect(page.locator(".quotes")).not.toContainText("4077.75");
});

test("keeps essential desktop trading labels legible", async ({ page }) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.goto("/");
  await expect(page.locator(".status-block small")).toHaveCSS("font-size", "10px");
  await expect(page.getByRole("button", { name: "Market desk" })).toHaveCSS("font-size", "12px");
  await expect(page.locator(".chart-options summary")).toHaveCSS("font-size", "12px");
  await expect(page.locator(".live-watch-metrics span").first()).toHaveCSS("font-size", "11px");
});

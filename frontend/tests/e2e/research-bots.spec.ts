import { expect, test, type Page } from "@playwright/test";

const observed = "2026-10-22T11:00:00Z";

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
  kill_switch_enabled: false, model_promotion_state: "REVIEW_REQUIRED", daily_research_failure_count: 0,
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
  strategy_ensemble: { ...liveResearch.strategy_ensemble, votes: [{ strategy_id: "STRUCTURE_ALIGNMENT", strategy_version: "structure-alignment-v1", decision: "WATCH_SHORT", reason_codes: [] }, { strategy_id: "MOMENTUM_ALIGNMENT", strategy_version: "momentum-alignment-v1", decision: "ABSTAIN", reason_codes: [] }, { strategy_id: "RANGE_BREAKOUT", strategy_version: "range-breakout-v1", decision: "ABSTAIN", reason_codes: [] }] },
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
  summary: "Automatic research watch is withheld because the independent rules or safety gates do not currently support a directional research watch.",
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
  await page.route("**/api/research", (route) => route.fulfill({ json: { ...values.research, live_research_watch: values.liveWatch ?? liveWatch } }));
  await page.route("**/api/research/validation", (route) => route.fulfill({ json: validation }));
  await page.route("**/api/research/operations", (route) => route.fulfill({ json: operations }));
  await page.route("**/api/sources/capabilities", (route) => route.fulfill({ json: sourceCapabilities }));
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "PUT") settings = { ...settings, ...JSON.parse(route.request().postData() ?? "{}") };
    await route.fulfill({ json: settings });
  });
}

test("clearly blocks market analysis when MT5 is disconnected", async ({ page }) => {
  await mockSnapshot(page, { connection: disconnected, quote: unavailableQuote, analysis: unavailableAnalysis, candles: unavailableCandles, research: unavailableResearch, liveWatch: unavailableLiveWatch });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Connect the terminal already signed in to your broker." })).toBeVisible();
  await expect(page.getByText("If you close MT5 later, PyonTrading disconnects and does not relaunch it.")).toBeVisible();
  await expect(page.getByText("No broker candles available")).toBeVisible();
  await expect(page.getByText("No price has been substituted.")).toHaveCount(0);
  await expect(page.getByLabel("Automatic live research watch")).toBeVisible();
  await expect(page.getByRole("heading", { name: "UNAVAILABLE" })).toBeVisible();
  await expect(page.getByText("Live status is automatic. Saving creates an optional audit snapshot.")).toBeVisible();
  await expect(page.getByText("What changes this", { exact: true })).toBeVisible();
  await expect(page.getByText("Broker quote: NOT_CONFIGURED")).toBeVisible();
});

test("renders live research bots and a no-execution market review", async ({ page }, testInfo) => {
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: liveAnalysis, candles: liveCandles, research: liveResearch });
  await page.route("**/api/research/analyze", (route) => route.fulfill({ json: marketReview }));

  await page.goto("/");

  await expect(page.getByLabel("Automatic live research watch")).toBeVisible();
  await expect(page.getByText("WITHHELD", { exact: true })).toBeVisible();
  await expect(page.getByText("Evidence coverage", { exact: true })).toBeVisible();
  await expect(page.getByText("Integrity", { exact: true })).toBeVisible();
  await expect(page.getByText("Research horizon", { exact: true })).toBeVisible();
  await expect(page.getByText("Not established", { exact: true })).toBeVisible();
  await expect(page.getByText("Observers", { exact: true })).toBeVisible();
  await expect(page.getByText("Ensemble", { exact: true })).toBeVisible();
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

  if (testInfo.project.name === "mobile-chrome") {
    await page.getByRole("button", { name: "Save review snapshot" }).click();
    await expect(page.getByRole("dialog").getByRole("heading", { name: "NO TRADE" })).toBeVisible();
    await page.getByRole("button", { name: "Close" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
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

  await page.getByRole("button", { name: "History" }).click();
  await expect(page.getByText("Recent research results")).toBeVisible();
  await expect(page.getByText("History keeps this source-labelled research result.")).toBeVisible();

  await page.getByRole("button", { name: "Research network", exact: true }).click();
  await page.getByRole("button", { name: "Save review snapshot" }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "NO TRADE" })).toBeVisible();
  await expect(page.getByText("M5 technical readings")).toBeVisible();
  await expect(page.getByText("Integrity & regime")).toBeVisible();
  await expect(page.getByText("Professional research modules")).toBeVisible();
  await expect(page.getByText("Estimated CVD")).toBeVisible();
  await expect(page.getByText("Independent-rule ensemble")).toBeVisible();
  await expect(page.getByText("4078.30 / 4085.61")).toBeVisible();
  await expect(page.getByLabel("Multi-timeframe broker-candle evidence")).toContainText("M5");
  await expect(page.getByText("NO ORDER EXECUTION", { exact: false }).last()).toBeVisible();
  await page.getByRole("button", { name: "Minimize" }).click();
  await expect(page.getByRole("complementary", { name: "Minimized market analysis" })).toBeVisible();
  await page.getByRole("button", { name: "Open" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("shows an aligned research watch without turning it into an order instruction", async ({ page }) => {
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
    lifecycle: "ACTIVE_RESEARCH_WATCH",
    direction: "SHORT_CONTEXT",
    evidence_score: 100,
    research_horizon: "MULTI_SESSION_CONTEXT",
    horizon_basis: "M5_M15_H1_H4_COMPLETED_CANDLES_ALIGNED",
    horizon_review_at_utc: "2026-10-22T04:00:00Z",
    horizon_reason_codes: ["M5_M15_H1_H4_COMPLETED_CANDLES_ALIGNED", "H4_CONTEXT_CONFIRMED"],
    summary: "Watch short is active as a completed-candle research watch until the next review. It is not a trade instruction, probability, or performance claim.",
    strategy_ensemble: watchResearch.strategy_ensemble,
  };
  await mockSnapshot(page, { connection: liveConnection, quote: liveQuote, analysis: watchAnalysis, candles: liveCandles, research: watchResearch, liveWatch: activeWatch });
  await page.route("**/api/research/analyze", (route) => route.fulfill({ json: watchReview }));

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "WATCH SHORT" })).toBeVisible();
  const watchSummary = page.locator(".live-watch-summary");
  await expect(watchSummary).toContainText("Automatic monitoring is active and withdraws when a source or rule changes.");
  await expect(watchSummary).toBeVisible();
  await expect(page.getByText("100/100")).toBeVisible();
  await expect(page.getByText("Multi-session context", { exact: true })).toBeVisible();
  await expect(page.getByText("M5 / M15 / H1 / H4 aligned", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Save review snapshot" }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "WATCH SHORT" })).toBeVisible();
  await expect(page.locator(".modal-gates .gate-watch")).toHaveText("WATCH");
  await expect(page.getByRole("dialog").getByText("No order execution", { exact: true })).toBeVisible();
});

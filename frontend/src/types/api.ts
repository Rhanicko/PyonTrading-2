export type DataStatus = "LIVE" | "DELAYED" | "STALE" | "DISCONNECTED" | "MARKET_CLOSED" | "NOT_CONFIGURED" | "HISTORY_INSUFFICIENT" | "SOURCE_ERROR";

export interface Envelope { source: string; source_timestamp_utc: string | null; observed_at_utc: string; data_status: DataStatus; reason_codes: string[]; }
export interface Connection extends Envelope { terminal_connected: boolean; terminal_path: string | null; broker_server: string | null; account_mode: "DEMO" | "LIVE" | "UNKNOWN"; configured_symbol: string | null; gold_symbols: { name: string; visible: boolean }[]; }
export interface Quote extends Envelope { symbol: string | null; bid: number | null; ask: number | null; spread_price: number | null; spread_points: number | null; tick_age_seconds: number | null; digits: number | null; raw_source_timestamp_utc?: string | null; broker_clock_offset_seconds?: number; timestamp_normalized?: boolean; }
export interface Candle { open_time_utc: string; open: number; high: number; low: number; close: number; tick_volume: number; completed: boolean; raw_open_time_utc?: string | null; broker_clock_offset_seconds?: number; timestamp_normalized?: boolean; }
export interface Candles extends Envelope { symbol: string | null; timeframe: string; candles: Candle[]; }
export interface Analysis extends Envelope { symbol: string | null; market_state: "DATA UNAVAILABLE" | "NO TRADE" | "WATCH LONG" | "WATCH SHORT"; direction_context: string; execution_gate: { label: string; state: string; reason: string }[]; }
export interface LocalSettings {
  symbol: string | null;
  timezone: "Asia/Manila";
  max_risk_percent: number;
  dxy_symbol: string | null;
  us10y_symbol: string | null;
  wti_symbol: string | null;
  volatility_symbol: string | null;
}
export interface SettingsUpdate extends Partial<LocalSettings> {}
export interface CalendarEvent { title: string; currency: "USD"; impact: "High" | "Medium" | "Low" | "Unknown"; event_time_utc: string; event_time_manila: string; forecast: string | null; previous: string | null; actual: string | null; source: string; source_url: string; }
export interface Events extends Envelope { source_url: string; events: CalendarEvent[]; }
export interface JournalEvaluation { id: number; evaluation_at_utc: string; symbol: string; timeframe: "M5"; candle_open_utc: string; quote_source_timestamp_utc: string | null; quote_bid: number | null; quote_ask: number | null; quote_status: DataStatus; market_state: "NO TRADE"; evaluation_type: "DATA_OBSERVATION"; strategy_version: string; reason_codes: string[]; }
export interface SignalJournal extends Envelope { evaluations: JournalEvaluation[]; }
export type ConfigurableStrategyId = "STRUCTURE_ALIGNMENT" | "MOMENTUM_ALIGNMENT" | "RANGE_BREAKOUT";
export interface StrategySetting { strategy_id: ConfigurableStrategyId; enabled: boolean; updated_at_utc: string | null; }
export interface StrategySettings extends Envelope { symbol: string | null; settings: StrategySetting[]; }
export interface SignalHistoryEntry {
  signal_id: string;
  provided_at_utc: string;
  symbol: string | null;
  source: string;
  source_timestamp_utc: string | null;
  data_status: DataStatus;
  analysis_mode: string;
  decision: "NO_TRADE" | "WATCH_LONG" | "WATCH_SHORT";
  market_context: "UPWARD_STRUCTURE" | "DOWNWARD_STRUCTURE" | "MIXED_STRUCTURE" | "UNAVAILABLE";
  summary: string;
  event_risk_state: string;
  paper_status: string | null;
  input_fingerprint: string;
  reason_codes: string[];
}
export interface SignalHistory extends Envelope { entries: SignalHistoryEntry[]; }
export interface HistoricalArchiveCoverage {
  source: string;
  broker_server: string | null;
  symbol: string;
  timeframe: string;
  completed_candles: number;
  first_open_utc: string | null;
  latest_open_utc: string | null;
  observed_span_days: number;
  readiness: "INSUFFICIENT" | "COLLECTING" | "WALK_FORWARD_READY";
  reason_codes: string[];
}
export interface SourceCapability {
  source_id: "MT5_TERMINAL" | "BROKER_CANDLES" | "BROKER_TICK_ACTIVITY" | "BROKER_DEPTH" | "USD_CALENDAR" | "CROSS_MARKET_CONTEXT" | "LICENSED_FUTURES_FLOW";
  label: string;
  data_status: DataStatus;
  state: "READY" | "ACTION_REQUIRED" | "UNAVAILABLE";
  source_category: VolumeSourceCategory;
  provider: string;
  summary: string;
  setup_hint: string;
  reason_codes: string[];
}
export interface SourceCapabilities extends Envelope { symbol: string | null; capabilities: SourceCapability[]; archives: HistoricalArchiveCoverage[]; }
export type VolumeSourceCategory = "BROKER_TICK_PROXY" | "ESTIMATED_DELTA" | "FUTURES_EXECUTED_FLOW" | "FUTURES_MARKET_DEPTH" | "UNAVAILABLE";
export interface StrategyJournalEvent { event_id: string; occurred_at_utc: string; symbol: string; candle_open_utc: string; strategy_id: string; strategy_version: string; state: string; direction: string; disposition: string; data_sources: VolumeSourceCategory[]; reason_codes: string[]; }
export interface StrategyJournal extends Envelope { events: StrategyJournalEvent[]; }
export interface ResearchBot { bot_id: "quality" | "chart" | "momentum" | "calendar" | "context" | "liquidity" | "volume" | "order_flow" | "risk" | "strategy" | "postmortem"; label: string; source: string; source_url: string | null; data_status: DataStatus; state: "OBSERVING" | "WATCHING" | "COLLECTING_EVIDENCE" | "BLOCKED"; source_timestamp_utc: string | null; updated_at_utc: string; summary: string; skills: string[]; facts: string[]; reason_codes: string[]; evidence_count: number; }
export interface TechnicalIndicators { ema_20: number | null; ema_60: number | null; rsi_14: number | null; atr_14: number | null; macd_histogram: number | null; adx_14: number | null; range_position_percent: number | null; latest_structure_event: string | null; active_fair_value_gaps: number | null; }
export interface TimeframeEvidence { timeframe: "M5" | "M15" | "H1" | "H4"; window_label: string; required_completed_candles: number; completed_candles: number; data_status: DataStatus; source_timestamp_utc: string | null; structure: "UPWARD_STRUCTURE" | "DOWNWARD_STRUCTURE" | "MIXED_STRUCTURE" | "UNAVAILABLE"; indicators?: TechnicalIndicators | null; reason_codes: string[]; }
export interface DataQuality { status: "CLEAR" | "WATCH" | "BLOCK"; quote_status: DataStatus; tick_age_seconds: number | null; spread_points: number | null; spread_baseline_points: number | null; spread_state: "NORMAL" | "ELEVATED" | "UNAVAILABLE"; candle_gap_count: number; timestamp_normalized: boolean; broker_clock_offset_seconds: number; broker_session_state: "LIVE_QUOTE" | "DELAYED_QUOTE" | "STALE_OR_CLOSED" | "UNAVAILABLE"; checked_at_utc: string; reason_codes: string[]; }
export interface SessionRegime { session_label: "ASIA" | "LONDON" | "NEW_YORK" | "LONDON_NEW_YORK_OVERLAP" | "OFF_HOURS" | "WEEKEND"; session_timezone_basis: string; volatility_regime: "LOW" | "NORMAL" | "ELEVATED" | "UNAVAILABLE"; market_regime: "TREND" | "RANGE" | "MIXED" | "UNAVAILABLE"; spread_state: "NORMAL" | "ELEVATED" | "UNAVAILABLE"; observed_at_utc: string; reason_codes: string[]; }
export interface CrossMarketFeature { key: "DXY" | "US10Y" | "WTI" | "VOLATILITY"; configured_symbol: string | null; data_status: DataStatus; source_timestamp_utc: string | null; return_20_bars_percent: number | null; summary: string; reason_codes: string[]; }
export interface OfficialMacroSource { provider: "BLS" | "BEA" | "FEDERAL_RESERVE"; source_url: string; data_status: DataStatus; retrieved_at_utc: string; source_timestamp_utc: string | null; next_release_title: string | null; next_release_at_utc: string | null; reason_codes: string[]; }
export interface LiquiditySweep { source_category: VolumeSourceCategory; data_status: DataStatus; state: string; direction: "BULLISH" | "BEARISH" | null; swept_level: number | null; absorption_state: string; reason_codes: string[]; }
export interface VolumeMomentum { source_category: VolumeSourceCategory; data_status: DataStatus; vwap: number | null; vwap_basis: string; relative_activity_ratio: number | null; relative_activity_basis: string; adx_14: number | null; state: string; direction: "BULLISH" | "BEARISH" | null; reason_codes: string[]; }
export interface EstimatedOrderFlow { source_category: VolumeSourceCategory; data_status: DataStatus; estimated_bar_delta: number | null; session_cvd: number | null; session_reset_basis: string; divergence: string; reason_codes: string[]; }
export interface VolumeProfile { source_category: VolumeSourceCategory; data_status: DataStatus; profile_basis: string; point_of_control: number | null; value_area_high: number | null; value_area_low: number | null; high_volume_nodes: number[]; low_volume_nodes: number[]; state: string; reason_codes: string[]; }
export interface OpeningRange { data_status: DataStatus; session: string; range_high: number | null; range_low: number | null; state: string; direction: "BULLISH" | "BEARISH" | null; reason_codes: string[]; }
export interface MarketDepth { source_category: VolumeSourceCategory; data_status: DataStatus; broker_depth_available: boolean; level_count: number; summary: string; reason_codes: string[]; }
export interface StrategyModule { strategy_id: string; strategy_version: string; state: string; direction: "WATCH_LONG" | "WATCH_SHORT" | "ABSTAIN"; data_sources: VolumeSourceCategory[]; summary: string; reason_codes: string[]; }
export interface RiskEngine { state: string; lifecycle_state: string; contract_specifications_available: boolean; quote_freshness_available: boolean; spread_available: boolean; event_risk_clear: boolean; costs_complete: boolean; reason_codes: string[]; }
export interface ProfessionalAnalysis { volume_source_category: VolumeSourceCategory; liquidity_sweep: LiquiditySweep; volume_momentum: VolumeMomentum; estimated_order_flow: EstimatedOrderFlow; volume_profile: VolumeProfile; opening_range: OpeningRange; market_depth: MarketDepth; strategy_modules: StrategyModule[]; risk_engine: RiskEngine; coordinator_state: "NO_TRADE" | "RESEARCH_WATCH" | "DATA_UNAVAILABLE"; reason_codes: string[]; }
export interface StrategyVote { strategy_id: "STRUCTURE_ALIGNMENT" | "MOMENTUM_ALIGNMENT" | "RANGE_BREAKOUT" | "LIQUIDITY_SWEEP_REVERSAL" | "VWAP_VOLUME_MOMENTUM" | "OPENING_RANGE_BREAKOUT" | "VOLUME_PROFILE_AUCTION" | "ORDER_FLOW_CONFIRMATION"; strategy_version: string; decision: "WATCH_LONG" | "WATCH_SHORT" | "ABSTAIN"; reason_codes: string[]; }
export interface StrategyEnsemble { decision: "NO_TRADE" | "WATCH_LONG" | "WATCH_SHORT"; confidence_state: "WITHHELD" | "REVIEW_REQUIRED"; votes: StrategyVote[]; agreement_count: number; required_agreement_count: number; model_promotion_state: "REVIEW_REQUIRED" | "NOT_APPROVED"; reason_codes: string[]; }
export interface PaperTrading { status: "NOT_CREATED" | "RECORDED" | "KILL_SWITCH_ENABLED"; candidate_id: string | null; expected_spread_points: number | null; commission_points: number | null; slippage_points: number | null; fill_quality_state: "UNAVAILABLE_NO_TICK_ARCHIVE" | "PENDING_OUTCOME" | "NOT_APPLICABLE"; reason_codes: string[]; }
export interface Operations { kill_switch_enabled: boolean; model_promotion_state: "REVIEW_REQUIRED" | "NOT_APPROVED"; daily_research_failure_count: number; alerts: string[]; latest_audit_at_utc: string | null; reason_codes: string[]; }
export interface ValidationSummary { symbol: string | null; total_frozen_decisions: number; paper_candidates: number; labelled_candidates: number; directional_matches: number; accuracy_percent: number | null; calibration_state: "INSUFFICIENT_LABELS" | "REVIEW_REQUIRED"; walk_forward: Record<string, number | null>; regime_counts: Record<string, number>; maximum_drawdown_points: number | null; cost_status: "SPREAD_ONLY" | "COSTS_INCOMPLETE"; reason_codes: string[]; }
export interface Research extends Envelope { symbol: string | null; research_window_hours: number; market_state: "DATA UNAVAILABLE" | "NO TRADE" | "WATCH LONG" | "WATCH SHORT"; validation_state: "NOT_VALIDATED"; analysis_timeframes: TimeframeEvidence[]; bots: ResearchBot[]; evidence_observations: number; data_quality: DataQuality | null; session_regime: SessionRegime | null; cross_market: CrossMarketFeature[]; official_macro_sources: OfficialMacroSource[]; event_risk_state: string; strategy_ensemble: StrategyEnsemble | null; professional_analysis: ProfessionalAnalysis | null; operations: Operations | null; live_research_watch: LiveResearchWatch | null; }
export interface LiveResearchWatch extends Envelope {
  symbol: string | null;
  lifecycle: "ACTIVE_RESEARCH_WATCH" | "WITHHELD" | "EXPIRED" | "UNAVAILABLE";
  direction: "LONG_CONTEXT" | "SHORT_CONTEXT" | "NONE";
  research_horizon?: "SHORT_HORIZON_CONTEXT" | "INTRADAY_CONTEXT" | "MULTI_SESSION_CONTEXT" | "UNAVAILABLE";
  horizon_basis?: string;
  horizon_review_at_utc?: string | null;
  horizon_reason_codes?: string[];
  evidence_score: number;
  evidence_score_basis: "EVIDENCE_COVERAGE_NOT_PROBABILITY";
  active_from_utc: string | null;
  scheduled_review_at_utc: string | null;
  expires_at_utc: string | null;
  summary: string;
  invalidation_conditions: string[];
  gates: { label: string; state: "PASS" | "WATCH" | "BLOCK"; reason: string }[];
  analysis_timeframes: TimeframeEvidence[];
  data_quality: DataQuality | null;
  event_risk_state: string;
  strategy_ensemble: StrategyEnsemble | null;
}
export interface MarketAnalysis extends Envelope { symbol: string | null; analysis_mode: "RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES"; decision: "NO_TRADE" | "WATCH_LONG" | "WATCH_SHORT"; market_context: "UPWARD_STRUCTURE" | "DOWNWARD_STRUCTURE" | "MIXED_STRUCTURE" | "UNAVAILABLE"; summary: string; gates: { label: string; state: "PASS" | "WATCH" | "BLOCK"; reason: string }[]; analysis_timeframes: TimeframeEvidence[]; supporting_facts: string[]; data_quality: DataQuality | null; session_regime: SessionRegime | null; cross_market: CrossMarketFeature[]; official_macro_sources: OfficialMacroSource[]; event_risk_state: string; strategy_ensemble: StrategyEnsemble | null; professional_analysis: ProfessionalAnalysis | null; paper_trading: PaperTrading | null; }
export interface BacktestStrategyResult { strategy_id: "PRICE_STRUCTURE_BASELINE" | "ICT_LIQUIDITY_REVERSAL" | "MOMENTUM_CONTINUATION" | "HTF_TREND_PULLBACK" | "LIQUIDITY_SWEEP_PROXY" | "VWAP_TICK_PROXY_MOMENTUM" | "OPENING_RANGE_BREAKOUT" | "VOLUME_PROFILE_PROXY_AUCTION" | "ORDER_FLOW_FUTURES_CONFIRMATION"; strategy_version: string; observed_signals: number; completed_trials: number; gross_wins: number; gross_losses: number; gross_points: number; net_points: number | null; reason_codes: string[]; }
export interface Backtest extends Envelope { run_id: string | null; symbol: string | null; timeframe: "M5"; dataset_start_utc: string | null; dataset_end_utc: string | null; completed_candles: number; results: BacktestStrategyResult[]; cost_model: string; limitation: string; }
export interface BarEvent { symbol: string | null; timeframe: string; data_status: DataStatus; reason_codes: string[]; candle: Candle; }
export interface LiveEvent { type: "quote" | "bar_update" | "bar_closed" | "provider_status" | "heartbeat"; sequence: number; observed_at_utc: string; payload: Quote | BarEvent | Envelope; }


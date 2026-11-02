from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataStatus(str, Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    MARKET_CLOSED = "MARKET_CLOSED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    HISTORY_INSUFFICIENT = "HISTORY_INSUFFICIENT"
    SOURCE_ERROR = "SOURCE_ERROR"


class ApiEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_version: Literal["v1"] = "v1"
    source: str = "MT5"
    source_timestamp_utc: datetime | None = None
    observed_at_utc: datetime
    data_status: DataStatus
    reason_codes: list[str] = Field(default_factory=list)


class SymbolSummary(BaseModel):
    name: str
    visible: bool


class ConnectionResponse(ApiEnvelope):
    terminal_connected: bool
    terminal_path: str | None = None
    broker_server: str | None = None
    account_mode: Literal["DEMO", "LIVE", "UNKNOWN"] = "UNKNOWN"
    configured_symbol: str | None = None
    gold_symbols: list[SymbolSummary] = Field(default_factory=list)


class SymbolsResponse(ApiEnvelope):
    """Exact instruments discovered from the connected local terminal."""

    source: str = "MT5"
    configured_symbol: str | None = None
    symbols: list[SymbolSummary] = Field(default_factory=list)


class QuoteResponse(ApiEnvelope):
    symbol: str | None = None
    bid: float | None = None
    ask: float | None = None
    spread_price: float | None = None
    spread_points: float | None = None
    tick_age_seconds: float | None = None
    digits: int | None = None
    point: float | None = None
    tick_size: float | None = None
    tick_value: float | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    volume_step: float | None = None
    contract_size: float | None = None
    stops_level_points: int | None = None
    freeze_level_points: int | None = None
    raw_source_timestamp_utc: datetime | None = None
    broker_clock_offset_seconds: int = 0
    timestamp_normalized: bool = False


class Candle(BaseModel):
    open_time_utc: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    real_volume: int | None = None
    spread_points: int | None = None
    completed: bool
    source: str = "MT5"
    raw_open_time_utc: datetime | None = None
    broker_clock_offset_seconds: int = 0
    timestamp_normalized: bool = False


class VolumeSourceCategory(str, Enum):
    """What the measurement represents, not how convincing it looks."""

    BROKER_TICK_PROXY = "BROKER_TICK_PROXY"
    ESTIMATED_DELTA = "ESTIMATED_DELTA"
    FUTURES_EXECUTED_FLOW = "FUTURES_EXECUTED_FLOW"
    FUTURES_MARKET_DEPTH = "FUTURES_MARKET_DEPTH"
    UNAVAILABLE = "UNAVAILABLE"


class LiquiditySweepReport(BaseModel):
    source_category: VolumeSourceCategory = VolumeSourceCategory.UNAVAILABLE
    data_status: DataStatus
    state: Literal["OBSERVING", "ARMED", "TRIGGERED", "UNAVAILABLE"] = "UNAVAILABLE"
    direction: Literal["BULLISH", "BEARISH"] | None = None
    swept_level: float | None = None
    level_known_at_utc: datetime | None = None
    confirmation_at_utc: datetime | None = None
    absorption_state: Literal["NOT_EVALUATED", "UNAVAILABLE_NO_EXECUTED_FLOW", "CONFIRMED_EXECUTED_FLOW"] = "NOT_EVALUATED"
    reason_codes: list[str] = Field(default_factory=list)


class VolumeMomentumReport(BaseModel):
    source_category: VolumeSourceCategory = VolumeSourceCategory.UNAVAILABLE
    data_status: DataStatus
    vwap: float | None = None
    vwap_basis: str = "UNAVAILABLE"
    relative_activity_ratio: float | None = Field(default=None, ge=0)
    relative_activity_basis: str = "UNAVAILABLE"
    adx_14: float | None = Field(default=None, ge=0, le=100)
    state: Literal["OBSERVING", "ARMED", "TRIGGERED", "UNAVAILABLE"] = "UNAVAILABLE"
    direction: Literal["BULLISH", "BEARISH"] | None = None
    reason_codes: list[str] = Field(default_factory=list)


class EstimatedOrderFlowReport(BaseModel):
    source_category: VolumeSourceCategory = VolumeSourceCategory.UNAVAILABLE
    data_status: DataStatus
    estimated_bar_delta: float | None = None
    session_cvd: float | None = None
    session_reset_basis: str = "UTC_DAY"
    divergence: Literal["BULLISH", "BEARISH", "NONE", "UNAVAILABLE"] = "UNAVAILABLE"
    reason_codes: list[str] = Field(default_factory=list)


class VolumeProfileReport(BaseModel):
    source_category: VolumeSourceCategory = VolumeSourceCategory.UNAVAILABLE
    data_status: DataStatus
    profile_basis: str = "UNAVAILABLE"
    point_of_control: float | None = None
    value_area_high: float | None = None
    value_area_low: float | None = None
    high_volume_nodes: list[float] = Field(default_factory=list)
    low_volume_nodes: list[float] = Field(default_factory=list)
    state: Literal["DEVELOPING_PROXY", "COMPLETED_PROXY", "UNAVAILABLE"] = "UNAVAILABLE"
    reason_codes: list[str] = Field(default_factory=list)


class OpeningRangeReport(BaseModel):
    data_status: DataStatus
    session: Literal["ASIA", "LONDON", "NEW_YORK", "OFF_HOURS"] = "OFF_HOURS"
    range_start_utc: datetime | None = None
    range_end_utc: datetime | None = None
    range_high: float | None = None
    range_low: float | None = None
    state: Literal["OBSERVING", "BREAKOUT", "FAILED_BREAKOUT", "UNAVAILABLE"] = "UNAVAILABLE"
    direction: Literal["BULLISH", "BEARISH"] | None = None
    reason_codes: list[str] = Field(default_factory=list)


class MarketDepthReport(BaseModel):
    source_category: VolumeSourceCategory = VolumeSourceCategory.UNAVAILABLE
    data_status: DataStatus
    broker_depth_available: bool = False
    level_count: int = Field(default=0, ge=0)
    summary: str
    reason_codes: list[str] = Field(default_factory=list)


class StrategyModuleReport(BaseModel):
    strategy_id: str
    strategy_version: str
    state: Literal["OBSERVING", "ARMED", "TRIGGERED", "REJECTED", "UNAVAILABLE"]
    direction: Literal["WATCH_LONG", "WATCH_SHORT", "ABSTAIN"] = "ABSTAIN"
    data_sources: list[VolumeSourceCategory] = Field(default_factory=list)
    summary: str
    reason_codes: list[str] = Field(default_factory=list)


class RiskEngineReport(BaseModel):
    state: Literal["REVIEW_REQUIRED", "REJECTED", "DATA_UNAVAILABLE"] = "DATA_UNAVAILABLE"
    lifecycle_state: Literal["OBSERVING", "ARMED", "TRIGGERED", "RISK_VALIDATED", "PAPER_ELIGIBLE", "REJECTED", "EXPIRED", "INVALIDATED", "DATA_UNAVAILABLE"] = "DATA_UNAVAILABLE"
    contract_specifications_available: bool = False
    quote_freshness_available: bool = False
    spread_available: bool = False
    event_risk_clear: bool = False
    costs_complete: bool = False
    reason_codes: list[str] = Field(default_factory=list)


class ProfessionalResearchReport(BaseModel):
    """Deterministic price/volume research. It cannot authorize an order."""

    volume_source_category: VolumeSourceCategory = VolumeSourceCategory.UNAVAILABLE
    liquidity_sweep: LiquiditySweepReport
    volume_momentum: VolumeMomentumReport
    estimated_order_flow: EstimatedOrderFlowReport
    volume_profile: VolumeProfileReport
    opening_range: OpeningRangeReport
    market_depth: MarketDepthReport
    strategy_modules: list[StrategyModuleReport] = Field(default_factory=list)
    risk_engine: RiskEngineReport
    coordinator_state: Literal["NO_TRADE", "RESEARCH_WATCH", "DATA_UNAVAILABLE"] = "DATA_UNAVAILABLE"
    reason_codes: list[str] = Field(default_factory=list)


class HistoricalArchiveCoverage(BaseModel):
    """Local completed-candle archive coverage; never a provider-performance claim."""

    source: str
    broker_server: str | None = None
    symbol: str
    timeframe: str
    completed_candles: int = Field(ge=0)
    first_open_utc: datetime | None = None
    latest_open_utc: datetime | None = None
    observed_span_days: float | None = Field(default=None, ge=0)
    readiness: Literal["INSUFFICIENT", "COLLECTING", "WALK_FORWARD_READY"] = "INSUFFICIENT"
    reason_codes: list[str] = Field(default_factory=list)


class SourceCapability(BaseModel):
    """A source setup check, with capability separate from current availability."""

    source_id: Literal[
        "MT5_TERMINAL", "BROKER_CANDLES", "BROKER_TICK_ACTIVITY", "BROKER_DEPTH",
        "USD_CALENDAR", "CROSS_MARKET_CONTEXT", "LICENSED_FUTURES_FLOW",
    ]
    label: str
    data_status: DataStatus
    state: Literal["READY", "ACTION_REQUIRED", "UNAVAILABLE"]
    source_category: VolumeSourceCategory = VolumeSourceCategory.UNAVAILABLE
    provider: str
    summary: str
    setup_hint: str
    reason_codes: list[str] = Field(default_factory=list)


class SourceCapabilitiesResponse(ApiEnvelope):
    source: str = "PYONTRADING2_SOURCE_SETUP"
    symbol: str | None = None
    capabilities: list[SourceCapability] = Field(default_factory=list)
    archives: list[HistoricalArchiveCoverage] = Field(default_factory=list)


class CandlesResponse(ApiEnvelope):
    symbol: str | None = None
    timeframe: str
    candles: list[Candle] = Field(default_factory=list)


class AnalysisResponse(ApiEnvelope):
    symbol: str | None = None
    market_state: Literal["DATA UNAVAILABLE", "NO TRADE", "WATCH LONG", "WATCH SHORT"] = "DATA UNAVAILABLE"
    direction_context: str = "Unavailable until verified broker candles are available."
    execution_gate: list[dict[str, str]] = Field(default_factory=list)


class CalendarEvent(BaseModel):
    title: str
    currency: Literal["USD"]
    impact: Literal["High", "Medium", "Low", "Unknown"] = "Unknown"
    event_time_utc: datetime
    event_time_manila: datetime
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None
    source: str = "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT"
    source_url: str


class EventsResponse(ApiEnvelope):
    source: str = "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT"
    source_url: str
    events: list[CalendarEvent] = Field(default_factory=list)


class JournalEvaluation(BaseModel):
    id: int
    evaluation_at_utc: datetime
    symbol: str
    timeframe: Literal["M5"]
    candle_open_utc: datetime
    quote_source_timestamp_utc: datetime | None = None
    quote_bid: float | None = None
    quote_ask: float | None = None
    quote_status: DataStatus
    market_state: Literal["NO TRADE"]
    evaluation_type: Literal["DATA_OBSERVATION"]
    strategy_version: str
    reason_codes: list[str] = Field(default_factory=list)


class SignalJournalResponse(ApiEnvelope):
    source: str = "MT5"
    evaluations: list[JournalEvaluation] = Field(default_factory=list)


StrategyId = Literal["STRUCTURE_ALIGNMENT", "MOMENTUM_ALIGNMENT", "RANGE_BREAKOUT"]


class StrategySetting(BaseModel):
    strategy_id: StrategyId
    enabled: bool
    updated_at_utc: datetime | None = None


class StrategySettingsResponse(ApiEnvelope):
    source: str = "PYONTRADING2_LOCAL_STRATEGY_SETTINGS"
    symbol: str | None = None
    settings: list[StrategySetting] = Field(default_factory=list)


class StrategySettingPayload(BaseModel):
    enabled: bool


class SignalHistoryEntry(BaseModel):
    """An immutable on-demand research result shown to the local user."""

    signal_id: str
    provided_at_utc: datetime
    symbol: str | None = None
    source: str
    source_timestamp_utc: datetime | None = None
    data_status: DataStatus
    analysis_mode: str
    decision: Literal["NO_TRADE", "WATCH_LONG", "WATCH_SHORT"]
    market_context: Literal["UPWARD_STRUCTURE", "DOWNWARD_STRUCTURE", "MIXED_STRUCTURE", "UNAVAILABLE"]
    summary: str
    event_risk_state: str
    paper_status: str | None = None
    input_fingerprint: str
    reason_codes: list[str] = Field(default_factory=list)


class SignalHistoryResponse(ApiEnvelope):
    source: str = "PYONTRADING2_SIGNAL_HISTORY"
    entries: list[SignalHistoryEntry] = Field(default_factory=list)


class StrategyJournalEvent(BaseModel):
    event_id: str
    occurred_at_utc: datetime
    symbol: str
    candle_open_utc: datetime
    strategy_id: str
    strategy_version: str
    state: str
    direction: str
    disposition: str
    data_sources: list[VolumeSourceCategory] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class StrategyJournalResponse(ApiEnvelope):
    source: str = "PYONTRADING2_STRATEGY_JOURNAL"
    events: list[StrategyJournalEvent] = Field(default_factory=list)


class ResearchBotReport(BaseModel):
    bot_id: Literal["quality", "chart", "momentum", "calendar", "context", "liquidity", "volume", "order_flow", "risk", "strategy", "postmortem"]
    label: str
    source: str
    source_url: str | None = None
    data_status: DataStatus
    state: Literal["OBSERVING", "WATCHING", "COLLECTING_EVIDENCE", "BLOCKED"]
    source_timestamp_utc: datetime | None = None
    updated_at_utc: datetime
    summary: str
    skills: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    evidence_count: int = Field(ge=0)


class DataQualityReport(BaseModel):
    """Integrity checks around the exact broker inputs used by research."""

    status: Literal["CLEAR", "WATCH", "BLOCK"] = "BLOCK"
    quote_status: DataStatus
    tick_age_seconds: float | None = None
    spread_points: float | None = None
    spread_baseline_points: float | None = None
    spread_state: Literal["NORMAL", "ELEVATED", "UNAVAILABLE"] = "UNAVAILABLE"
    candle_gap_count: int = Field(default=0, ge=0)
    timestamp_normalized: bool = False
    broker_clock_offset_seconds: int = 0
    broker_session_state: Literal["LIVE_QUOTE", "DELAYED_QUOTE", "STALE_OR_CLOSED", "UNAVAILABLE"] = "UNAVAILABLE"
    checked_at_utc: datetime
    reason_codes: list[str] = Field(default_factory=list)


class SessionRegimeReport(BaseModel):
    """Descriptive market-session and realised-regime context, never a forecast."""

    session_label: Literal["ASIA", "LONDON", "NEW_YORK", "LONDON_NEW_YORK_OVERLAP", "OFF_HOURS", "WEEKEND"]
    session_timezone_basis: str = "IANA_MARKET_SESSION_TIMEZONES"
    volatility_regime: Literal["LOW", "NORMAL", "ELEVATED", "UNAVAILABLE"] = "UNAVAILABLE"
    market_regime: Literal["TREND", "RANGE", "MIXED", "UNAVAILABLE"] = "UNAVAILABLE"
    spread_state: Literal["NORMAL", "ELEVATED", "UNAVAILABLE"] = "UNAVAILABLE"
    observed_at_utc: datetime
    reason_codes: list[str] = Field(default_factory=list)


class CrossMarketFeature(BaseModel):
    key: Literal["DXY", "US10Y", "WTI", "VOLATILITY"]
    configured_symbol: str | None = None
    data_status: DataStatus
    source_timestamp_utc: datetime | None = None
    return_20_bars_percent: float | None = None
    summary: str
    reason_codes: list[str] = Field(default_factory=list)


class OfficialMacroSource(BaseModel):
    provider: Literal["BLS", "BEA", "FEDERAL_RESERVE"]
    source_url: str
    data_status: DataStatus
    retrieved_at_utc: datetime
    source_timestamp_utc: datetime | None = None
    next_release_title: str | None = None
    next_release_at_utc: datetime | None = None
    reason_codes: list[str] = Field(default_factory=list)


class StrategyVote(BaseModel):
    strategy_id: Literal["STRUCTURE_ALIGNMENT", "MOMENTUM_ALIGNMENT", "RANGE_BREAKOUT", "LIQUIDITY_SWEEP_REVERSAL", "VWAP_VOLUME_MOMENTUM", "OPENING_RANGE_BREAKOUT", "VOLUME_PROFILE_AUCTION", "ORDER_FLOW_CONFIRMATION"]
    strategy_version: str
    decision: Literal["WATCH_LONG", "WATCH_SHORT", "ABSTAIN"]
    reason_codes: list[str] = Field(default_factory=list)


class StrategyEnsemble(BaseModel):
    decision: Literal["NO_TRADE", "WATCH_LONG", "WATCH_SHORT"] = "NO_TRADE"
    confidence_state: Literal["WITHHELD", "REVIEW_REQUIRED"] = "WITHHELD"
    votes: list[StrategyVote] = Field(default_factory=list)
    agreement_count: int = Field(default=0, ge=0)
    required_agreement_count: int = Field(default=2, ge=2)
    model_promotion_state: Literal["REVIEW_REQUIRED", "NOT_APPROVED"] = "REVIEW_REQUIRED"
    reason_codes: list[str] = Field(default_factory=list)


class PaperTradingReport(BaseModel):
    status: Literal["NOT_CREATED", "RECORDED", "KILL_SWITCH_ENABLED"] = "NOT_CREATED"
    candidate_id: str | None = None
    expected_spread_points: float | None = None
    commission_points: float | None = None
    slippage_points: float | None = None
    fill_quality_state: Literal["UNAVAILABLE_NO_TICK_ARCHIVE", "PENDING_OUTCOME", "NOT_APPLICABLE"] = "NOT_APPLICABLE"
    reason_codes: list[str] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    symbol: str | None = None
    total_frozen_decisions: int = Field(ge=0)
    paper_candidates: int = Field(ge=0)
    labelled_candidates: int = Field(ge=0)
    directional_matches: int = Field(ge=0)
    accuracy_percent: float | None = Field(default=None, ge=0, le=100)
    calibration_state: Literal["INSUFFICIENT_LABELS", "REVIEW_REQUIRED"]
    walk_forward: dict[str, int | float | None] = Field(default_factory=dict)
    regime_counts: dict[str, int] = Field(default_factory=dict)
    maximum_drawdown_points: float | None = None
    cost_status: Literal["SPREAD_ONLY", "COSTS_INCOMPLETE"] = "COSTS_INCOMPLETE"
    reason_codes: list[str] = Field(default_factory=list)


class OperationsStatus(BaseModel):
    kill_switch_enabled: bool = False
    model_promotion_state: Literal["REVIEW_REQUIRED", "NOT_APPROVED"] = "REVIEW_REQUIRED"
    daily_research_failure_count: int = Field(default=0, ge=0)
    alerts: list[str] = Field(default_factory=list)
    latest_audit_at_utc: datetime | None = None
    reason_codes: list[str] = Field(default_factory=list)


class KillSwitchPayload(BaseModel):
    enabled: bool


class TechnicalIndicators(BaseModel):
    """Completed-candle technical context for a research timeframe.

    These values are descriptive measurements, not entry, exit, or execution
    instructions. They are omitted when the source window is unavailable.
    """

    ema_20: float | None = None
    ema_60: float | None = None
    rsi_14: float | None = Field(default=None, ge=0, le=100)
    atr_14: float | None = Field(default=None, ge=0)
    macd_histogram: float | None = None
    adx_14: float | None = Field(default=None, ge=0, le=100)
    range_position_percent: float | None = Field(default=None, ge=0, le=100)
    latest_structure_event: str | None = None
    active_fair_value_gaps: int | None = Field(default=None, ge=0)


class TimeframeEvidence(BaseModel):
    """Broker-candle evidence used by the multi-timeframe research screen."""

    timeframe: Literal["M5", "M15", "H1", "H4"]
    window_label: str
    required_completed_candles: int = Field(ge=1)
    completed_candles: int = Field(ge=0)
    data_status: DataStatus
    source_timestamp_utc: datetime | None = None
    structure: Literal["UPWARD_STRUCTURE", "DOWNWARD_STRUCTURE", "MIXED_STRUCTURE", "UNAVAILABLE"] = "UNAVAILABLE"
    indicators: TechnicalIndicators | None = None
    reason_codes: list[str] = Field(default_factory=list)


class ResearchResponse(ApiEnvelope):
    source: str = "PYONTRADING2_RESEARCH_COORDINATOR"
    symbol: str | None = None
    research_window_hours: int = Field(default=12, ge=1)
    market_state: Literal["DATA UNAVAILABLE", "NO TRADE", "WATCH LONG", "WATCH SHORT"] = "DATA UNAVAILABLE"
    validation_state: Literal["NOT_VALIDATED"] = "NOT_VALIDATED"
    analysis_timeframes: list[TimeframeEvidence] = Field(default_factory=list)
    bots: list[ResearchBotReport] = Field(default_factory=list)
    evidence_observations: int = Field(ge=0)
    data_quality: DataQualityReport | None = None
    session_regime: SessionRegimeReport | None = None
    cross_market: list[CrossMarketFeature] = Field(default_factory=list)
    official_macro_sources: list[OfficialMacroSource] = Field(default_factory=list)
    # Exact calendar gate retained with the observation so an archived decision
    # can be audited without reconstructing live calendar state later.
    event_risk_state: str = "UNVERIFIED"
    strategy_ensemble: StrategyEnsemble | None = None
    professional_analysis: ProfessionalResearchReport | None = None
    operations: OperationsStatus | None = None
    # Derived from this exact source snapshot so the workstation does not run
    # a second concurrent MT5 research pass merely to render the live watch.
    live_research_watch: LiveResearchWatchResponse | None = None


class LiveResearchWatchResponse(ApiEnvelope):
    """Automatic, completed-candle research watch with explicit abstention states.

    This is deliberately not a trade ticket.  The score is evidence coverage,
    not a probability, performance estimate, or confidence claim.
    """

    source: str = "PYONTRADING2_LIVE_RESEARCH_WATCH"
    symbol: str | None = None
    lifecycle: Literal["ACTIVE_RESEARCH_WATCH", "WITHHELD", "EXPIRED", "UNAVAILABLE"] = "UNAVAILABLE"
    direction: Literal["LONG_CONTEXT", "SHORT_CONTEXT", "NONE"] = "NONE"
    # This classifies the completed-candle evidence breadth. It is not an
    # expected holding period, a timing recommendation, or an order signal.
    research_horizon: Literal[
        "SHORT_HORIZON_CONTEXT",
        "INTRADAY_CONTEXT",
        "MULTI_SESSION_CONTEXT",
        "UNAVAILABLE",
    ] = "UNAVAILABLE"
    horizon_basis: str = "COMPLETED_CANDLE_EVIDENCE_REQUIRED"
    horizon_review_at_utc: datetime | None = None
    horizon_reason_codes: list[str] = Field(default_factory=list)
    evidence_score: int = Field(default=0, ge=0, le=100)
    evidence_score_basis: str = "EVIDENCE_COVERAGE_NOT_PROBABILITY"
    active_from_utc: datetime | None = None
    scheduled_review_at_utc: datetime | None = None
    expires_at_utc: datetime | None = None
    summary: str
    invalidation_conditions: list[str] = Field(default_factory=list)
    gates: list[dict[str, str]] = Field(default_factory=list)
    analysis_timeframes: list[TimeframeEvidence] = Field(default_factory=list)
    data_quality: DataQualityReport | None = None
    event_risk_state: str = "UNVERIFIED"
    strategy_ensemble: StrategyEnsemble | None = None


class MarketAnalysisResponse(ApiEnvelope):
    source: str = "PYONTRADING2_RESEARCH_SCREEN"
    symbol: str | None = None
    analysis_mode: Literal["RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES"] = "RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES"
    decision: Literal["NO_TRADE", "WATCH_LONG", "WATCH_SHORT"] = "NO_TRADE"
    market_context: Literal["UPWARD_STRUCTURE", "DOWNWARD_STRUCTURE", "MIXED_STRUCTURE", "UNAVAILABLE"] = "UNAVAILABLE"
    summary: str
    gates: list[dict[str, str]] = Field(default_factory=list)
    analysis_timeframes: list[TimeframeEvidence] = Field(default_factory=list)
    supporting_facts: list[str] = Field(default_factory=list)
    data_quality: DataQualityReport | None = None
    session_regime: SessionRegimeReport | None = None
    cross_market: list[CrossMarketFeature] = Field(default_factory=list)
    official_macro_sources: list[OfficialMacroSource] = Field(default_factory=list)
    event_risk_state: str = "UNVERIFIED"
    strategy_ensemble: StrategyEnsemble | None = None
    professional_analysis: ProfessionalResearchReport | None = None
    paper_trading: PaperTradingReport | None = None


class BacktestStrategyResult(BaseModel):
    strategy_id: Literal["PRICE_STRUCTURE_BASELINE", "ICT_LIQUIDITY_REVERSAL", "MOMENTUM_CONTINUATION", "HTF_TREND_PULLBACK", "LIQUIDITY_SWEEP_PROXY", "VWAP_TICK_PROXY_MOMENTUM", "OPENING_RANGE_BREAKOUT", "VOLUME_PROFILE_PROXY_AUCTION", "ORDER_FLOW_FUTURES_CONFIRMATION"]
    strategy_version: str
    observed_signals: int = Field(ge=0)
    completed_trials: int = Field(ge=0)
    gross_wins: int = Field(ge=0)
    gross_losses: int = Field(ge=0)
    gross_points: float
    net_points: float | None = None
    reason_codes: list[str] = Field(default_factory=list)


class BacktestResponse(ApiEnvelope):
    source: str = "PYONTRADING2_BACKTEST_LAB"
    run_id: str | None = None
    symbol: str | None = None
    timeframe: Literal["M5"] = "M5"
    dataset_start_utc: datetime | None = None
    dataset_end_utc: datetime | None = None
    completed_candles: int = Field(ge=0)
    results: list[BacktestStrategyResult] = Field(default_factory=list)
    cost_model: str
    limitation: str


class BacktestRunSummary(BaseModel):
    run_id: str
    created_at_utc: datetime
    symbol: str
    timeframe: Literal["M5"]
    completed_candles: int = Field(ge=0)
    data_status: DataStatus
    reason_codes: list[str] = Field(default_factory=list)


class BacktestHistoryResponse(ApiEnvelope):
    source: str = "PYONTRADING2_BACKTEST_LAB"
    runs: list[BacktestRunSummary] = Field(default_factory=list)


class ResearchModelSummary(BaseModel):
    model_version_id: str
    created_at_utc: datetime
    model_kind: str
    model_version: str
    state: str
    symbol: str
    timeframe: str
    dataset_start_utc: datetime | None = None
    dataset_end_utc: datetime | None = None
    dataset_candles: int = Field(ge=0)
    feature_set_version: str
    reason_codes: list[str] = Field(default_factory=list)


class ResearchModelsResponse(ApiEnvelope):
    source: str = "PYONTRADING2_TRAINING_REGISTRY"
    models: list[ResearchModelSummary] = Field(default_factory=list)


class KronosStatusResponse(ApiEnvelope):
    """Optional experiment status; disabled is an honest operational state."""

    source: str = "PYONTRADING2_KRONOS_LAB"
    state: Literal["DISABLED", "NOT_AVAILABLE"] = "NOT_AVAILABLE"
    enabled: bool = False
    model_version: str | None = None
    reason: str


class KronosForecastsResponse(KronosStatusResponse):
    forecasts: list[dict[str, object]] = Field(default_factory=list)


class SettingsPayload(BaseModel):
    symbol: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,32}$")
    timezone: Literal["Asia/Manila"] = "Asia/Manila"
    max_risk_percent: float = Field(default=0.5, ge=0.1, le=1.0)
    dxy_symbol: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,32}$")
    us10y_symbol: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,32}$")
    wti_symbol: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,32}$")
    volatility_symbol: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,32}$")


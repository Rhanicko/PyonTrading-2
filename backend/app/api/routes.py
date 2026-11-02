from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from secrets import compare_digest
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.market.timeframes import TIMEFRAME_NAMES
from app.config import settings
from app.services.cross_market import CrossMarketSymbols
from app.schemas.market import (
    AnalysisResponse,
    BacktestHistoryResponse,
    BacktestResponse,
    CandlesResponse,
    DataStatus,
    EventsResponse,
    JournalEvaluation,
    KillSwitchPayload,
    KronosForecastsResponse,
    KronosStatusResponse,
    LiveResearchWatchResponse,
    MarketAnalysisResponse,
    OperationsStatus,
    ResearchModelsResponse,
    ResearchResponse,
    SettingsPayload,
    SignalHistoryEntry,
    SignalHistoryResponse,
    SignalJournalResponse,
    SourceCapabilitiesResponse,
    StrategyJournalEvent,
    StrategyJournalResponse,
    StrategySetting,
    StrategySettingPayload,
    StrategySettingsResponse,
    SymbolsResponse,
    ValidationSummary,
)
from app.storage.database import (
    read_operations_status,
    read_recent_backtest_runs,
    read_recent_evaluations,
    read_recent_model_versions,
    read_recent_signal_history,
    read_recent_strategy_journal_events,
    read_settings,
    read_strategy_settings,
    read_validation_summary,
    record_signal_history,
    write_operation_control,
    write_settings,
    write_strategy_setting,
)


router = APIRouter(prefix="/api")


def service(request: Request):
    return request.app.state.live_service


def require_operator_token(x_pyon_operator_token: str | None = Header(default=None)) -> None:
    """Control mutations require an explicitly configured local operator secret."""
    if not settings.operator_token or not x_pyon_operator_token or not compare_digest(settings.operator_token, x_pyon_operator_token):
        raise HTTPException(status_code=403, detail={"reason_codes": ["OPERATOR_TOKEN_REQUIRED"], "message": "Configure PYON_OPERATOR_TOKEN and supply X-Pyon-Operator-Token."})


@router.get("/health")
def health(request: Request):
    live = service(request)
    connection = live.adapter.connection(live.configured_symbol)
    return {
        "source": "PYONTRADING2", "source_timestamp_utc": connection.source_timestamp_utc,
        "observed_at_utc": datetime.now(UTC), "data_status": connection.data_status,
        "reason_codes": connection.reason_codes, "ready": True, "mt5_terminal_connected": connection.terminal_connected,
    }


@router.get("/connection")
def connection(request: Request):
    live = service(request)
    return live.adapter.connection(live.configured_symbol)


@router.get("/symbols", response_model=SymbolsResponse)
def symbols(request: Request):
    """Expose only exact broker-discovered XAUUSD aliases; no alias guessing."""
    live = service(request)
    current = live.adapter.connection(live.configured_symbol)
    return SymbolsResponse(
        observed_at_utc=datetime.now(UTC),
        source_timestamp_utc=current.source_timestamp_utc,
        data_status=current.data_status,
        reason_codes=current.reason_codes,
        configured_symbol=live.configured_symbol,
        symbols=current.gold_symbols,
    )


@router.get("/quote")
def quote(request: Request, symbol: str | None = Query(default=None, pattern=r"^[A-Za-z0-9._-]{1,32}$")):
    live = service(request)
    if symbol and live.configured_symbol and symbol != live.configured_symbol:
        raise HTTPException(status_code=409, detail={"reason_codes": ["SYMBOL_NOT_CONFIGURED"]})
    return live.adapter.quote(symbol or live.configured_symbol)


@router.get("/candles")
def candles(
    request: Request,
    symbol: str | None = Query(default=None, pattern=r"^[A-Za-z0-9._-]{1,32}$"),
    tf: str = Query(default="M5"),
    limit: int = Query(default=300, ge=2, le=2000),
):
    if tf not in TIMEFRAME_NAMES:
        raise HTTPException(status_code=422, detail={"reason_codes": ["UNSUPPORTED_TIMEFRAME"]})
    live = service(request)
    selected = symbol or live.configured_symbol
    status, reasons, values = live.adapter.candles(selected, tf, limit)
    return CandlesResponse(
        observed_at_utc=datetime.now(UTC), data_status=status, reason_codes=reasons,
        symbol=selected, timeframe=tf, candles=values,
    )


@router.get("/analysis")
def analysis(request: Request, symbol: str | None = Query(default=None, pattern=r"^[A-Za-z0-9._-]{1,32}$")):
    live = service(request)
    selected = symbol or live.configured_symbol
    research_snapshot = request.app.state.research_service.snapshot(selected)
    quote_snapshot = live.adapter.quote(selected)
    quote_available = quote_snapshot.data_status == DataStatus.LIVE
    available = quote_available and research_snapshot.market_state != "DATA UNAVAILABLE"
    professional = research_snapshot.professional_analysis
    return AnalysisResponse(
        observed_at_utc=datetime.now(UTC), source_timestamp_utc=quote_snapshot.source_timestamp_utc,
        data_status=quote_snapshot.data_status, reason_codes=quote_snapshot.reason_codes or (["COMPLETED_CANDLE_RESEARCH_ONLY", "NO_ORDER_EXECUTION"] if available else ["QUOTE_NOT_LIVE"]),
        symbol=selected, market_state=research_snapshot.market_state if available else "DATA UNAVAILABLE",
        direction_context=(
            f"{research_snapshot.market_state.title()} research condition: completed-candle rules agree, but it remains a source-labelled research watch and not an order instruction."
            if research_snapshot.market_state in {"WATCH LONG", "WATCH SHORT"} else
            "Source-labelled completed-candle liquidity, volume-proxy, opening-range and risk research is available. No order instruction is produced."
            if available else "No verified quote or completed multi-strategy candle set is available."
        ),
        execution_gate=[
            {"label": "Broker quote", "state": "PASS" if quote_available else "BLOCK", "reason": "LIVE" if quote_available else quote_snapshot.data_status.value},
            {"label": "Completed-candle strategy research", "state": "PASS" if research_snapshot.analysis_timeframes else "BLOCK", "reason": "MULTI_TIMEFRAME_COMPLETED" if research_snapshot.analysis_timeframes else "HISTORY_INSUFFICIENT"},
            {"label": "Independent risk review", "state": "PASS" if professional and professional.risk_engine.state == "REVIEW_REQUIRED" else "BLOCK", "reason": professional.risk_engine.state if professional else "DATA_UNAVAILABLE"},
        ],
    )


@router.get("/signals", response_model=SignalJournalResponse)
def signals(request: Request):
    live = service(request)
    quote_snapshot = live.latest_quote or live.adapter.quote(live.configured_symbol)
    return SignalJournalResponse(
        observed_at_utc=datetime.now(UTC),
        source_timestamp_utc=quote_snapshot.source_timestamp_utc,
        data_status=quote_snapshot.data_status,
        reason_codes=["DATA_ONLY_JOURNAL", "IMMUTABLE_COMPLETED_CANDLE_OBSERVATIONS", "NO_ORDER_EXECUTION"],
        evaluations=[JournalEvaluation(**item) for item in read_recent_evaluations(request.app.state.database_path)],
    )


@router.get("/signals/history", response_model=SignalHistoryResponse)
def signal_history(request: Request, limit: int = Query(default=12, ge=1, le=50)):
    """List immutable research screens returned after a local Analyze market request."""
    live = service(request)
    quote_snapshot = live.latest_quote or live.adapter.quote(live.configured_symbol)
    return SignalHistoryResponse(
        observed_at_utc=datetime.now(UTC), source_timestamp_utc=quote_snapshot.source_timestamp_utc,
        data_status=quote_snapshot.data_status,
        reason_codes=["USER_REQUESTED_RESEARCH_HISTORY", "IMMUTABLE_EVIDENCE_PAYLOAD", "NO_ORDER_EXECUTION"],
        entries=[SignalHistoryEntry(**item) for item in read_recent_signal_history(
            request.app.state.database_path, symbol=live.configured_symbol, limit=limit,
        )],
    )


@router.get("/strategy-journal", response_model=StrategyJournalResponse)
def strategy_journal(request: Request):
    live = service(request)
    quote_snapshot = live.latest_quote or live.adapter.quote(live.configured_symbol)
    return StrategyJournalResponse(
        observed_at_utc=datetime.now(UTC), source_timestamp_utc=quote_snapshot.source_timestamp_utc,
        data_status=quote_snapshot.data_status,
        reason_codes=["APPEND_ONLY_STRATEGY_EVENTS", "RESEARCH_ONLY", "NO_ORDER_EXECUTION"],
        events=[StrategyJournalEvent(**item) for item in read_recent_strategy_journal_events(
            request.app.state.database_path, symbol=live.configured_symbol,
        )],
    )


@router.get("/events", response_model=EventsResponse)
def events(request: Request, scope: Literal["upcoming", "today"] = Query(default="upcoming")):
    return request.app.state.calendar_service.upcoming_usd_events(limit=8, today_only=scope == "today")


@router.get("/calendar", response_model=EventsResponse)
def calendar(request: Request, scope: Literal["upcoming", "today"] = Query(default="upcoming")):
    """Named calendar endpoint backed by the same source-aware event adapter."""
    return events(request, scope)


@router.get("/sources/capabilities", response_model=SourceCapabilitiesResponse)
def source_capabilities(request: Request):
    """On-demand setup checks; no provider credential is accepted or retained."""
    live = service(request)
    return request.app.state.source_setup_service.snapshot(live.configured_symbol)


@router.get("/research", response_model=ResearchResponse)
def research(request: Request):
    live = service(request)
    # This screen refreshes frequently for source status, so it deliberately
    # reads the latest completed-candle research without manufacturing durable
    # evidence rows. The background pipeline owns persisted evidence.
    return request.app.state.research_service.snapshot(live.configured_symbol, persist_evidence=False)


@router.get("/research/live-watch", response_model=LiveResearchWatchResponse)
def live_research_watch(request: Request):
    """Automatic research-only watch; this route does not save a manual review or place orders."""
    live = service(request)
    return request.app.state.research_service.live_research_watch(live.configured_symbol)


@router.get("/research/pipeline")
def research_pipeline(request: Request):
    """Worker-process status and durable research records, separate from live market status."""
    return request.app.state.research_pipeline.status()


@router.get("/research/jobs")
def research_jobs(request: Request):
    """Expose the actual background-worker state and durable job counters."""
    return request.app.state.research_pipeline.status()


@router.get("/research/models", response_model=ResearchModelsResponse)
def research_models(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    """Read the local review-only model/strategy registry, never model artifacts."""
    live = service(request)
    quote_snapshot = live.latest_quote or live.adapter.quote(live.configured_symbol)
    return ResearchModelsResponse(
        observed_at_utc=datetime.now(UTC),
        source_timestamp_utc=quote_snapshot.source_timestamp_utc,
        data_status=quote_snapshot.data_status,
        reason_codes=["LOCAL_RESEARCH_REGISTRY", "MANUAL_PROMOTION_REQUIRED", "NO_ORDER_EXECUTION"],
        models=read_recent_model_versions(
            request.app.state.database_path, symbol=live.configured_symbol, limit=limit,
        ),
    )


@router.get("/research/strategies", response_model=StrategySettingsResponse)
def research_strategies(request: Request):
    """Return effective owner strategy choices for the configured symbol."""
    live = service(request)
    quote_snapshot = live.latest_quote or live.adapter.quote(live.configured_symbol)
    stored = read_strategy_settings(request.app.state.database_path, symbol=live.configured_symbol)
    strategy_ids = ("STRUCTURE_ALIGNMENT", "MOMENTUM_ALIGNMENT", "RANGE_BREAKOUT")
    return StrategySettingsResponse(
        observed_at_utc=datetime.now(UTC),
        source_timestamp_utc=quote_snapshot.source_timestamp_utc,
        data_status=quote_snapshot.data_status,
        reason_codes=["LOCAL_OWNER_CONFIGURATION", "COMPLETED_CANDLE_RESEARCH_ONLY", "NO_ORDER_EXECUTION"],
        symbol=live.configured_symbol,
        settings=[
            StrategySetting(
                strategy_id=strategy_id,
                enabled=stored.get(strategy_id, {}).get("enabled", True),
                updated_at_utc=stored.get(strategy_id, {}).get("updated_at_utc"),
            )
            for strategy_id in strategy_ids
        ],
    )


@router.put("/research/strategies/{strategy_id}", response_model=StrategySettingsResponse)
def update_research_strategy(
    strategy_id: Literal["STRUCTURE_ALIGNMENT", "MOMENTUM_ALIGNMENT", "RANGE_BREAKOUT"],
    payload: StrategySettingPayload,
    request: Request,
    _operator: None = Depends(require_operator_token),
):
    """Persist an explicit local owner toggle; it cannot rewrite past evidence."""
    live = service(request)
    if not live.configured_symbol:
        raise HTTPException(status_code=409, detail={"reason_codes": ["SYMBOL_NOT_CONFIGURED"]})
    write_strategy_setting(
        request.app.state.database_path,
        symbol=live.configured_symbol,
        strategy_id=strategy_id,
        enabled=payload.enabled,
    )
    return research_strategies(request)


@router.get("/research/validation", response_model=ValidationSummary)
def research_validation(request: Request):
    live = service(request)
    return ValidationSummary(**read_validation_summary(request.app.state.database_path, symbol=live.configured_symbol))


@router.get("/research/operations", response_model=OperationsStatus)
def research_operations(request: Request):
    return OperationsStatus(**read_operations_status(request.app.state.database_path))


@router.post("/research/operations/kill-switch", response_model=OperationsStatus)
def set_paper_kill_switch(
    payload: KillSwitchPayload,
    request: Request,
    _operator: None = Depends(require_operator_token),
):
    write_operation_control(
        request.app.state.database_path,
        key="paper_kill_switch",
        value="true" if payload.enabled else "false",
        actor="LOCAL_OPERATOR",
        action="PAPER_KILL_SWITCH_UPDATED",
    )
    return OperationsStatus(**read_operations_status(request.app.state.database_path))


@router.get("/macro/official")
def official_macro(request: Request):
    """Official schedule provenance only; this endpoint never invents release values."""
    return {"sources": [item.model_dump(mode="json") for item in request.app.state.official_macro_service.snapshot()]}


@router.get("/kronos/status", response_model=KronosStatusResponse)
def kronos_status(request: Request):
    """Kronos remains absent until its upstream package and model weights are vetted."""
    live = service(request)
    quote_snapshot = live.latest_quote or live.adapter.quote(live.configured_symbol)
    return KronosStatusResponse(
        observed_at_utc=datetime.now(UTC),
        source_timestamp_utc=quote_snapshot.source_timestamp_utc,
        data_status=DataStatus.NOT_CONFIGURED,
        reason_codes=["OPTIONAL_EXPERIMENT_NOT_INSTALLED", "UPSTREAM_LICENSE_AND_WEIGHT_REVIEW_REQUIRED", "NO_SIGNAL_AUTHORITY"],
        reason="Kronos has not been installed or given model weights. Core research does not depend on it.",
    )


@router.get("/kronos/forecasts", response_model=KronosForecastsResponse)
def kronos_forecasts(request: Request):
    """Return an explicit empty state rather than manufactured forecast paths."""
    status = kronos_status(request)
    return KronosForecastsResponse(**status.model_dump(), forecasts=[])


@router.post("/research/analyze", response_model=MarketAnalysisResponse)
def analyze_research(request: Request):
    live = service(request)
    analysis = request.app.state.research_service.analyze_market(live.configured_symbol)
    payload = analysis.model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    record_signal_history(
        request.app.state.database_path,
        signal_id=uuid4().hex,
        provided_at_utc=analysis.observed_at_utc,
        symbol=analysis.symbol,
        source=analysis.source,
        source_timestamp_utc=analysis.source_timestamp_utc,
        data_status=analysis.data_status.value,
        analysis_mode=analysis.analysis_mode,
        decision=analysis.decision,
        market_context=analysis.market_context,
        summary=analysis.summary,
        event_risk_state=analysis.event_risk_state,
        paper_status=analysis.paper_trading.status if analysis.paper_trading else None,
        input_fingerprint=fingerprint,
        reason_codes=analysis.reason_codes,
        payload=payload,
    )
    return analysis


@router.post("/backtests/run", response_model=BacktestResponse)
def run_backtest(request: Request):
    live = service(request)
    return request.app.state.backtest_service.run(live.configured_symbol)


@router.get("/backtests", response_model=BacktestHistoryResponse)
def backtest_history(request: Request):
    live = service(request)
    quote_snapshot = live.latest_quote or live.adapter.quote(live.configured_symbol)
    return BacktestHistoryResponse(
        observed_at_utc=datetime.now(UTC), source_timestamp_utc=quote_snapshot.source_timestamp_utc,
        data_status=quote_snapshot.data_status,
        reason_codes=["IMMUTABLE_RESEARCH_RUNS", "NO_ORDER_EXECUTION"],
        runs=read_recent_backtest_runs(request.app.state.database_path),
    )


@router.get("/settings")
def get_settings(request: Request):
    local = read_settings(request.app.state.database_path)
    def context_value(key: str, fallback: str | None) -> str | None:
        return (local[key] if key in local else fallback) or None

    return {
        "symbol": local.get("symbol"), "timezone": local.get("timezone", "Asia/Manila"),
        "max_risk_percent": float(local.get("max_risk_percent", "0.5")),
        "dxy_symbol": context_value("dxy_symbol", settings.dxy_symbol),
        "us10y_symbol": context_value("us10y_symbol", settings.us10y_symbol),
        "wti_symbol": context_value("wti_symbol", settings.wti_symbol),
        "volatility_symbol": context_value("volatility_symbol", settings.volatility_symbol),
    }


@router.put("/settings")
def update_settings(payload: SettingsPayload, request: Request):
    live = service(request)
    local = read_settings(request.app.state.database_path)
    selected_symbol = payload.symbol if payload.symbol is not None else live.configured_symbol
    if selected_symbol:
        connection = live.adapter.connection(live.configured_symbol)
        available = {item.name for item in connection.gold_symbols}
        if selected_symbol not in available:
            raise HTTPException(status_code=422, detail={"reason_codes": ["SYMBOL_NOT_DISCOVERED"], "message": "Choose an exact gold symbol discovered from the connected MT5 terminal."})
    context_fields = ("dxy_symbol", "us10y_symbol", "wti_symbol", "volatility_symbol")
    requested_context = {
        field: getattr(payload, field)
        for field in context_fields
        if field in payload.model_fields_set
    }
    for field, symbol in requested_context.items():
        if symbol is None:
            continue
        enabled, reasons = live.adapter.enable_context_symbol(symbol)
        if not enabled:
            raise HTTPException(status_code=422, detail={"reason_codes": reasons, "message": f"The exact {field} symbol was not available from this MT5 terminal."})
    values = {"timezone": payload.timezone, "max_risk_percent": str(payload.max_risk_percent)}
    if payload.symbol is not None:
        values["symbol"] = selected_symbol or ""
    for field, symbol in requested_context.items():
        values[field] = symbol or ""
    write_settings(request.app.state.database_path, values)
    live.set_configured_symbol(selected_symbol)
    configured_context = CrossMarketSymbols(
        dxy=(requested_context["dxy_symbol"] if "dxy_symbol" in requested_context else local.get("dxy_symbol") if "dxy_symbol" in local else settings.dxy_symbol) or None,
        us10y=(requested_context["us10y_symbol"] if "us10y_symbol" in requested_context else local.get("us10y_symbol") if "us10y_symbol" in local else settings.us10y_symbol) or None,
        wti=(requested_context["wti_symbol"] if "wti_symbol" in requested_context else local.get("wti_symbol") if "wti_symbol" in local else settings.wti_symbol) or None,
        volatility=(requested_context["volatility_symbol"] if "volatility_symbol" in requested_context else local.get("volatility_symbol") if "volatility_symbol" in local else settings.volatility_symbol) or None,
    )
    request.app.state.cross_market_service.set_symbols(configured_context)
    return {"saved": True, **get_settings(request), "symbol": selected_symbol}


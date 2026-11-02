"""Completed-candle volume, liquidity and auction research.

The local MT5 feed can expose broker tick activity.  That is useful as a
participation proxy, but it is not consolidated XAUUSD volume, GC futures
executed flow, or a futures order book.  This module keeps that distinction in
every result and deliberately emits unavailable states when stronger data is
not connected.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from app.analysis.technical import TechnicalSnapshot, analyze_completed_candles, completed_candles
from app.schemas.market import (
    Candle,
    DataQualityReport,
    DataStatus,
    EstimatedOrderFlowReport,
    LiquiditySweepReport,
    MarketDepthReport,
    OpeningRangeReport,
    ProfessionalResearchReport,
    QuoteResponse,
    RiskEngineReport,
    StrategyModuleReport,
    VolumeMomentumReport,
    VolumeProfileReport,
    VolumeSourceCategory,
)


M5 = timedelta(minutes=5)


def _unavailable(status: DataStatus, reason: str) -> ProfessionalResearchReport:
    liquidity = LiquiditySweepReport(data_status=status, reason_codes=[reason])
    momentum = VolumeMomentumReport(data_status=status, reason_codes=[reason])
    order_flow = EstimatedOrderFlowReport(data_status=status, reason_codes=[reason])
    profile = VolumeProfileReport(data_status=status, reason_codes=[reason])
    opening = OpeningRangeReport(data_status=status, reason_codes=[reason])
    depth = MarketDepthReport(
        data_status=status,
        summary="Market-depth analysis is unavailable without a verified provider snapshot.",
        reason_codes=[reason],
    )
    risk = RiskEngineReport(
        state="DATA_UNAVAILABLE", lifecycle_state="DATA_UNAVAILABLE", reason_codes=[reason],
    )
    return ProfessionalResearchReport(
        liquidity_sweep=liquidity, volume_momentum=momentum, estimated_order_flow=order_flow,
        volume_profile=profile, opening_range=opening, market_depth=depth, risk_engine=risk,
        coordinator_state="DATA_UNAVAILABLE", reason_codes=[reason, "NO_ORDER_EXECUTION"],
    )


def _volume_source(values: list[Candle]) -> VolumeSourceCategory:
    return VolumeSourceCategory.BROKER_TICK_PROXY if values and any(bar.tick_volume > 0 for bar in values) else VolumeSourceCategory.UNAVAILABLE


def _relative_activity(values: list[Candle]) -> tuple[float | None, str]:
    """Compare the latest completed bar only with prior same-slot broker bars.

    A five-minute slot repeats every 288 bars.  At least two historical values
    are required so a thin session cannot be called exceptional by accident.
    """
    if len(values) < 289:
        return None, "INSUFFICIENT_TIME_OF_DAY_BASELINE"
    current = values[-1]
    prior = [bar.tick_volume for bar in values[:-1] if bar.open_time_utc.time() == current.open_time_utc.time()]
    if len(prior) < 2:
        return None, "INSUFFICIENT_TIME_OF_DAY_BASELINE"
    baseline = median(prior)
    if baseline <= 0:
        return None, "ZERO_TIME_OF_DAY_BASELINE"
    return current.tick_volume / baseline, "SAME_UTC_TIME_OF_DAY_MEDIAN"


def volume_momentum(values: list[Candle], snapshot: TechnicalSnapshot) -> VolumeMomentumReport:
    source = _volume_source(values)
    if source == VolumeSourceCategory.UNAVAILABLE:
        return VolumeMomentumReport(data_status=DataStatus.HISTORY_INSUFFICIENT, reason_codes=["TICK_ACTIVITY_UNAVAILABLE"])
    total_weight = sum(max(bar.tick_volume, 0) for bar in values)
    if total_weight <= 0:
        return VolumeMomentumReport(data_status=DataStatus.HISTORY_INSUFFICIENT, reason_codes=["TICK_ACTIVITY_UNAVAILABLE"])
    vwap = sum(((bar.high + bar.low + bar.close) / 3) * max(bar.tick_volume, 0) for bar in values) / total_weight
    relative_activity, activity_basis = _relative_activity(values)
    current = values[-1]
    direction: str | None = None
    state: str = "OBSERVING"
    if snapshot.adx_14 is not None and snapshot.adx_14 >= 20 and relative_activity is not None and relative_activity >= 1.1:
        if current.close > vwap and snapshot.trend_context == "EMA_BULLISH":
            direction, state = "BULLISH", "ARMED"
        elif current.close < vwap and snapshot.trend_context == "EMA_BEARISH":
            direction, state = "BEARISH", "ARMED"
    return VolumeMomentumReport(
        source_category=source, data_status=DataStatus.LIVE, vwap=vwap,
        vwap_basis="TYPICAL_PRICE_WEIGHTED_BY_BROKER_TICK_ACTIVITY",
        relative_activity_ratio=relative_activity, relative_activity_basis=activity_basis,
        adx_14=snapshot.adx_14, state=state, direction=direction,
        reason_codes=[
            "BROKER_TICK_ACTIVITY_NOT_EXECUTED_VOLUME",
            "COMPLETED_CANDLES_ONLY",
            "NO_ORDER_EXECUTION",
        ],
    )


def estimated_order_flow(values: list[Candle]) -> EstimatedOrderFlowReport:
    source = _volume_source(values)
    if source == VolumeSourceCategory.UNAVAILABLE:
        return EstimatedOrderFlowReport(data_status=DataStatus.HISTORY_INSUFFICIENT, reason_codes=["ESTIMATED_DELTA_UNAVAILABLE"])
    current_day = values[-1].open_time_utc.astimezone(UTC).date()
    session_values = [bar for bar in values if bar.open_time_utc.astimezone(UTC).date() == current_day]
    deltas = [
        float(bar.tick_volume) if bar.close > bar.open else -float(bar.tick_volume) if bar.close < bar.open else 0.0
        for bar in session_values
    ]
    return EstimatedOrderFlowReport(
        source_category=VolumeSourceCategory.ESTIMATED_DELTA, data_status=DataStatus.LIVE,
        estimated_bar_delta=deltas[-1] if deltas else None, session_cvd=sum(deltas),
        divergence="NONE", reason_codes=[
            "PRICE_DIRECTION_CLASSIFICATION_ONLY",
            "BROKER_TICK_ACTIVITY_NOT_EXECUTED_VOLUME",
            "NOT_GENUINE_FUTURES_ORDER_FLOW",
            "UTC_DAY_RESET",
        ],
    )


def volume_profile(values: list[Candle], point: float | None) -> VolumeProfileReport:
    source = _volume_source(values)
    if source == VolumeSourceCategory.UNAVAILABLE or point is None or point <= 0:
        return VolumeProfileReport(data_status=DataStatus.HISTORY_INSUFFICIENT, reason_codes=["VOLUME_PROFILE_PROXY_INPUT_UNAVAILABLE"])
    # MT5 OHLC bars do not contain volume-at-price. Assigning each bar's tick
    # count to its completed close is an explicitly limited proxy, never a
    # footprint or exchange profile.
    bins: dict[float, float] = defaultdict(float)
    for bar in values:
        price_bin = round(round(bar.close / point) * point, 10)
        bins[price_bin] += max(bar.tick_volume, 0)
    if not bins:
        return VolumeProfileReport(data_status=DataStatus.HISTORY_INSUFFICIENT, reason_codes=["VOLUME_PROFILE_PROXY_INPUT_UNAVAILABLE"])
    poc = min(bins, key=lambda price: (-bins[price], price))
    total = sum(bins.values())
    selected: list[float] = []
    running = 0.0
    # Tie-breaking is deterministic: higher activity first, then closer to POC,
    # then lower price.  It is recorded in the report reason codes.
    for price in sorted(bins, key=lambda item: (-bins[item], abs(item - poc), item)):
        selected.append(price)
        running += bins[price]
        if running >= total * 0.70:
            break
    ranked = sorted(bins, key=lambda price: (-bins[price], price))
    low_ranked = sorted(bins, key=lambda price: (bins[price], price))
    return VolumeProfileReport(
        source_category=source, data_status=DataStatus.LIVE,
        profile_basis="COMPLETED_BAR_CLOSE_BUCKETED_BROKER_TICK_ACTIVITY",
        point_of_control=poc, value_area_high=max(selected), value_area_low=min(selected),
        high_volume_nodes=ranked[:3], low_volume_nodes=low_ranked[:3], state="DEVELOPING_PROXY",
        reason_codes=[
            "BROKER_TICK_ACTIVITY_NOT_EXECUTED_VOLUME",
            "CLOSE_BUCKET_PROXY_NOT_VOLUME_AT_PRICE",
            "VALUE_AREA_70_PERCENT_DETERMINISTIC_TIE_BREAK",
            "COMPLETED_CANDLES_ONLY",
        ],
    )


def liquidity_sweep(values: list[Candle], snapshot: TechnicalSnapshot, point: float | None) -> LiquiditySweepReport:
    if len(values) < 8 or not snapshot.swings:
        return LiquiditySweepReport(data_status=DataStatus.HISTORY_INSUFFICIENT, reason_codes=["CONFIRMED_SWING_HISTORY_INSUFFICIENT"])
    current = values[-1]
    tolerance = max((snapshot.atr_14 or 0) * 0.05, point or 0.0)
    available = [swing for swing in snapshot.swings if swing.known_at <= current.open_time_utc]
    highs = [swing for swing in available if swing.kind == "HIGH"]
    lows = [swing for swing in available if swing.kind == "LOW"]
    latest_structure = snapshot.structure_events[-1] if snapshot.structure_events else None
    if highs:
        high = highs[-1]
        if current.high >= high.price + tolerance and current.close < high.price:
            confirmed = latest_structure is not None and latest_structure.direction == "BEARISH"
            return LiquiditySweepReport(
                source_category=VolumeSourceCategory.BROKER_TICK_PROXY, data_status=DataStatus.LIVE,
                state="TRIGGERED" if confirmed else "ARMED", direction="BEARISH", swept_level=high.price,
                level_known_at_utc=high.known_at, confirmation_at_utc=current.open_time_utc + M5 if confirmed else None,
                absorption_state="UNAVAILABLE_NO_EXECUTED_FLOW",
                reason_codes=["COMPLETED_CANDLE_RECLAIM", "CONFIRMED_SWING_LEVEL", "ABSORPTION_REQUIRES_FUTURES_EXECUTED_FLOW", "NO_ORDER_EXECUTION"],
            )
    if lows:
        low = lows[-1]
        if current.low <= low.price - tolerance and current.close > low.price:
            confirmed = latest_structure is not None and latest_structure.direction == "BULLISH"
            return LiquiditySweepReport(
                source_category=VolumeSourceCategory.BROKER_TICK_PROXY, data_status=DataStatus.LIVE,
                state="TRIGGERED" if confirmed else "ARMED", direction="BULLISH", swept_level=low.price,
                level_known_at_utc=low.known_at, confirmation_at_utc=current.open_time_utc + M5 if confirmed else None,
                absorption_state="UNAVAILABLE_NO_EXECUTED_FLOW",
                reason_codes=["COMPLETED_CANDLE_RECLAIM", "CONFIRMED_SWING_LEVEL", "ABSORPTION_REQUIRES_FUTURES_EXECUTED_FLOW", "NO_ORDER_EXECUTION"],
            )
    return LiquiditySweepReport(
        source_category=VolumeSourceCategory.BROKER_TICK_PROXY, data_status=DataStatus.LIVE,
        state="OBSERVING", absorption_state="UNAVAILABLE_NO_EXECUTED_FLOW",
        reason_codes=["NO_COMPLETED_CANDLE_SWEEP", "ABSORPTION_REQUIRES_FUTURES_EXECUTED_FLOW"],
    )


def _active_session(current: datetime) -> tuple[str, datetime, datetime] | None:
    """Return a session window with IANA daylight-saving handling."""
    definitions = (
        ("ASIA", "Asia/Tokyo", time(0, 0), timedelta(hours=1)),
        ("LONDON", "Europe/London", time(8, 0), timedelta(minutes=30)),
        ("NEW_YORK", "America/New_York", time(9, 30), timedelta(minutes=30)),
    )
    for label, timezone_name, start_time, duration in definitions:
        local = current.astimezone(ZoneInfo(timezone_name))
        start_local = datetime.combine(local.date(), start_time, tzinfo=local.tzinfo)
        if start_local <= local < start_local + timedelta(hours=8):
            return label, start_local.astimezone(UTC), (start_local + duration).astimezone(UTC)
    return None


def opening_range(values: list[Candle]) -> OpeningRangeReport:
    if not values:
        return OpeningRangeReport(data_status=DataStatus.HISTORY_INSUFFICIENT, reason_codes=["OPENING_RANGE_HISTORY_INSUFFICIENT"])
    current = values[-1].open_time_utc + M5
    active = _active_session(current)
    if active is None:
        return OpeningRangeReport(data_status=DataStatus.LIVE, reason_codes=["OUTSIDE_CONFIGURED_OPENING_RANGE_SESSION"])
    session, start, end = active
    bars = [bar for bar in values if start <= bar.open_time_utc < end]
    if not bars or current < end:
        return OpeningRangeReport(
            data_status=DataStatus.LIVE, session=session, range_start_utc=start, range_end_utc=end,
            state="OBSERVING", reason_codes=["OPENING_RANGE_STILL_FORMING", "COMPLETED_CANDLES_ONLY"],
        )
    high, low = max(bar.high for bar in bars), min(bar.low for bar in bars)
    latest = values[-1]
    if latest.close > high:
        state, direction = "BREAKOUT", "BULLISH"
    elif latest.close < low:
        state, direction = "BREAKOUT", "BEARISH"
    else:
        state, direction = "OBSERVING", None
    return OpeningRangeReport(
        data_status=DataStatus.LIVE, session=session, range_start_utc=start, range_end_utc=end,
        range_high=high, range_low=low, state=state, direction=direction,
        reason_codes=["IANA_SESSION_TIMEZONE", "COMPLETED_CANDLES_ONLY"],
    )


def risk_engine(
    quote: QuoteResponse,
    calendar_state: str,
    module_reports: list[StrategyModuleReport],
    data_quality: DataQualityReport | None = None,
) -> RiskEngineReport:
    """Apply the single veto layer after independent module observations.

    This function deliberately returns only research eligibility. It has no
    sizing, entry, stop, target, or broker-order capability.
    """
    quote_current = quote.data_status == DataStatus.LIVE and quote.tick_age_seconds is not None
    contract = all(value is not None and value > 0 for value in (quote.point, quote.tick_size, quote.tick_value, quote.volume_min, quote.volume_step, quote.contract_size))
    spread = quote.spread_points is not None and quote.spread_points >= 0
    event_clear = calendar_state not in {"HIGH_IMPACT_WINDOW", "ELEVATED_EVENT_WINDOW", "UNVERIFIED"}
    directions = {report.direction for report in module_reports if report.direction != "ABSTAIN" and report.state in {"ARMED", "TRIGGERED"}}
    reasons: list[str] = ["NO_ORDER_EXECUTION", "COMMISSION_UNAVAILABLE", "SLIPPAGE_UNAVAILABLE", "STRUCTURAL_STOP_NOT_PUBLISHED"]
    if not quote_current:
        reasons.append("QUOTE_FRESHNESS_UNAVAILABLE")
    if not contract:
        reasons.append("BROKER_CONTRACT_SPECIFICATIONS_INCOMPLETE")
    if not spread:
        reasons.append("SPREAD_UNAVAILABLE")
    if not event_clear:
        reasons.append("EVENT_RISK_GATE_NOT_CLEAR")
    if len(directions) > 1:
        reasons.append("CONFLICTING_STRATEGY_DIRECTIONS")
    # A WATCH remains explicit in the report, but it is not the same as a
    # broken current data feed. Only a blocking integrity state or an
    # elevated spread vetoes a source-labelled research watch condition.
    integrity_blocked = data_quality is not None and (
        data_quality.status == "BLOCK" or data_quality.spread_state == "ELEVATED"
    )
    if data_quality is not None:
        if data_quality.status == "BLOCK":
            reasons.append("DATA_QUALITY_BLOCK")
        elif data_quality.status == "WATCH":
            reasons.append("DATA_QUALITY_WATCH")
        if data_quality.spread_state == "ELEVATED":
            reasons.append("ELEVATED_SPREAD_GATE")
    if not quote_current or not contract or not spread or (data_quality is not None and data_quality.status == "BLOCK"):
        state, lifecycle = "DATA_UNAVAILABLE", "DATA_UNAVAILABLE"
    elif integrity_blocked or not event_clear or len(directions) > 1:
        state, lifecycle = "REJECTED", "REJECTED"
    else:
        state, lifecycle = "REVIEW_REQUIRED", "OBSERVING"
    return RiskEngineReport(
        state=state, lifecycle_state=lifecycle, contract_specifications_available=contract,
        quote_freshness_available=quote_current, spread_available=spread, event_risk_clear=event_clear,
        costs_complete=False, reason_codes=reasons,
    )


def professional_research(
    candles: list[Candle],
    quote: QuoteResponse,
    calendar_state: str,
    market_depth: MarketDepthReport | None = None,
    cross_market_available: bool = False,
    data_quality: DataQualityReport | None = None,
) -> ProfessionalResearchReport:
    """Build source-labelled research without producing order parameters."""
    values = completed_candles(candles)
    if len(values) < 60:
        return _unavailable(quote.data_status if quote.data_status != DataStatus.LIVE else DataStatus.HISTORY_INSUFFICIENT, "COMPLETED_CANDLE_HISTORY_INSUFFICIENT")
    snapshot = analyze_completed_candles(values, M5)
    momentum = volume_momentum(values, snapshot)
    sweep = liquidity_sweep(values, snapshot, quote.point)
    estimated_flow = estimated_order_flow(values)
    profile = volume_profile(values, quote.point)
    opening = opening_range(values)
    depth = market_depth or MarketDepthReport(
        data_status=DataStatus.NOT_CONFIGURED,
        summary="No licensed futures order-flow or market-depth provider is configured.",
        reason_codes=["LICENSED_FUTURES_ORDER_FLOW_NOT_CONFIGURED", "MT5_BROKER_DEPTH_NOT_REQUESTED"],
    )
    modules = [
        StrategyModuleReport(
            strategy_id="LIQUIDITY_SWEEP_REVERSAL", strategy_version="liquidity-sweep-reversal-v1",
            state=sweep.state, direction=("WATCH_LONG" if sweep.direction == "BULLISH" else "WATCH_SHORT" if sweep.direction == "BEARISH" else "ABSTAIN"),
            data_sources=[sweep.source_category], summary="Confirmed-swing sweep/reclaim research; absorption remains unavailable without executed futures flow.",
            reason_codes=sweep.reason_codes,
        ),
        StrategyModuleReport(
            strategy_id="VWAP_VOLUME_MOMENTUM", strategy_version="vwap-tick-proxy-momentum-v1",
            state=momentum.state, direction=("WATCH_LONG" if momentum.direction == "BULLISH" else "WATCH_SHORT" if momentum.direction == "BEARISH" else "ABSTAIN"),
            data_sources=[momentum.source_category], summary="VWAP and participation are broker tick-activity proxies, not executed volume.",
            reason_codes=momentum.reason_codes,
        ),
        StrategyModuleReport(
            strategy_id="ESTIMATED_ORDER_FLOW", strategy_version="estimated-delta-proxy-v1",
            state="OBSERVING" if estimated_flow.data_status == DataStatus.LIVE else "UNAVAILABLE",
            direction="ABSTAIN", data_sources=[estimated_flow.source_category],
            summary="Estimated delta/CVD classifies broker tick activity by completed-bar price direction; it is not executed futures flow.",
            reason_codes=estimated_flow.reason_codes,
        ),
        StrategyModuleReport(
            strategy_id="OPENING_RANGE_BREAKOUT", strategy_version="session-opening-range-v1",
            state="TRIGGERED" if opening.state == "BREAKOUT" else "OBSERVING" if opening.state == "OBSERVING" else "UNAVAILABLE",
            direction=("WATCH_LONG" if opening.direction == "BULLISH" else "WATCH_SHORT" if opening.direction == "BEARISH" else "ABSTAIN"),
            data_sources=[VolumeSourceCategory.BROKER_TICK_PROXY], summary="Timezone-aware completed-candle session opening-range research.",
            reason_codes=opening.reason_codes,
        ),
        StrategyModuleReport(
            strategy_id="VOLUME_PROFILE_AUCTION", strategy_version="close-bucket-tick-proxy-profile-v1",
            state="OBSERVING" if profile.data_status == DataStatus.LIVE else "UNAVAILABLE", direction="ABSTAIN",
            data_sources=[profile.source_category], summary="Profile is a close-bucket tick-activity proxy; authentic volume-at-price is unavailable.",
            reason_codes=profile.reason_codes,
        ),
        StrategyModuleReport(
            strategy_id="MARKET_DEPTH", strategy_version="broker-depth-provenance-v1",
            state="OBSERVING" if depth.broker_depth_available else "UNAVAILABLE", direction="ABSTAIN",
            data_sources=[depth.source_category],
            summary="Broker depth availability is retained separately; it is not consolidated futures market depth.",
            reason_codes=depth.reason_codes,
        ),
        StrategyModuleReport(
            strategy_id="CROSS_MARKET_CONTEXT", strategy_version="configured-context-v1",
            state="OBSERVING" if cross_market_available else "UNAVAILABLE", direction="ABSTAIN",
            data_sources=[], summary="Configured DXY, Treasury-yield, oil and volatility series are contextual features, not causal proof.",
            reason_codes=["CONTEXT_ONLY_NOT_CAUSAL"] if cross_market_available else ["CROSS_MARKET_SYMBOLS_NOT_CONFIGURED"],
        ),
    ]
    risk = risk_engine(quote, calendar_state, modules, data_quality=data_quality)
    active_directions = {module.direction for module in modules if module.state in {"ARMED", "TRIGGERED"} and module.direction != "ABSTAIN"}
    coordinator_state = "RESEARCH_WATCH" if len(active_directions) == 1 and risk.state == "REVIEW_REQUIRED" else "NO_TRADE"
    return ProfessionalResearchReport(
        volume_source_category=_volume_source(values), liquidity_sweep=sweep, volume_momentum=momentum,
        estimated_order_flow=estimated_flow, volume_profile=profile, opening_range=opening,
        market_depth=depth, strategy_modules=modules, risk_engine=risk,
        coordinator_state=coordinator_state,
        reason_codes=[
            "DETERMINISTIC_COMPLETED_CANDLE_RESEARCH",
            "NO_EXECUTED_FUTURES_FLOW" if depth.source_category == VolumeSourceCategory.UNAVAILABLE else "FUTURES_FLOW_SOURCE_RETAINED",
            "NO_ORDER_EXECUTION",
        ],
    )

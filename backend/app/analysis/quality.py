from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.market import Candle, DataQualityReport, DataStatus, QuoteResponse, SessionRegimeReport


def assess_data_quality(
    quote: QuoteResponse,
    candles: list[Candle],
    *,
    timeframe: timedelta,
    now: datetime | None = None,
) -> DataQualityReport:
    """Evaluate observable MT5 input integrity without manufacturing a quality score."""
    checked_at = now or datetime.now(UTC)
    completed = sorted((bar for bar in candles if bar.completed), key=lambda bar: bar.open_time_utc)
    gaps = sum(
        later.open_time_utc - earlier.open_time_utc > timeframe * 1.5
        for earlier, later in zip(completed, completed[1:], strict=False)
    )
    historical_spreads = [float(bar.spread_points) for bar in completed[-60:] if bar.spread_points is not None and bar.spread_points >= 0]
    baseline = median(historical_spreads) if historical_spreads else None
    if quote.spread_points is None or baseline is None or baseline <= 0:
        spread_state = "UNAVAILABLE"
    elif quote.spread_points > baseline * 2.5:
        spread_state = "ELEVATED"
    else:
        spread_state = "NORMAL"

    reasons = list(quote.reason_codes)
    if gaps:
        reasons.append("CANDLE_GAPS_DETECTED")
    if spread_state == "ELEVATED":
        reasons.append("SPREAD_ABOVE_RECENT_MEDIAN")
    if baseline is None:
        reasons.append("SPREAD_HISTORY_UNAVAILABLE")
    if quote.timestamp_normalized:
        reasons.append("BROKER_CLOCK_OFFSET_RETAINED")

    if quote.data_status != DataStatus.LIVE:
        status = "BLOCK"
        broker_session_state = "STALE_OR_CLOSED" if quote.data_status in {DataStatus.STALE, DataStatus.MARKET_CLOSED} else "UNAVAILABLE"
    elif gaps or spread_state == "ELEVATED":
        status = "WATCH"
        broker_session_state = "LIVE_QUOTE"
    else:
        status = "CLEAR"
        broker_session_state = "LIVE_QUOTE"
    if quote.data_status == DataStatus.DELAYED:
        broker_session_state = "DELAYED_QUOTE"

    return DataQualityReport(
        status=status,
        quote_status=quote.data_status,
        tick_age_seconds=quote.tick_age_seconds,
        spread_points=quote.spread_points,
        spread_baseline_points=baseline,
        spread_state=spread_state,
        candle_gap_count=gaps,
        timestamp_normalized=quote.timestamp_normalized,
        broker_clock_offset_seconds=quote.broker_clock_offset_seconds,
        broker_session_state=broker_session_state,
        checked_at_utc=checked_at,
        reason_codes=list(dict.fromkeys(reasons)),
    )


def classify_session_and_regime(
    candles: list[Candle],
    *,
    structure: str,
    spread_state: str,
    now: datetime | None = None,
) -> SessionRegimeReport:
    """Return timezone-aware session labels and completed-bar realised regime labels."""
    observed_at = now or datetime.now(UTC)
    session, timezone_basis = _session_context(observed_at)
    completed = sorted((bar for bar in candles if bar.completed), key=lambda bar: bar.open_time_utc)
    reasons = ["COMPLETED_CANDLES_ONLY", "SESSION_LABEL_IS_DESCRIPTIVE"]
    if len(completed) < 40:
        return SessionRegimeReport(
            session_label=session,
            session_timezone_basis=timezone_basis,
            volatility_regime="UNAVAILABLE",
            market_regime="UNAVAILABLE",
            spread_state=spread_state if spread_state in {"NORMAL", "ELEVATED"} else "UNAVAILABLE",
            observed_at_utc=observed_at,
            reason_codes=[*reasons, "REGIME_HISTORY_INSUFFICIENT"],
        )
    recent_ranges = [bar.high - bar.low for bar in completed[-20:]]
    reference_ranges = [bar.high - bar.low for bar in completed[-120:-20]]
    recent_average = sum(recent_ranges) / len(recent_ranges)
    reference_average = sum(reference_ranges) / len(reference_ranges) if reference_ranges else 0.0
    if reference_average <= 0:
        volatility = "UNAVAILABLE"
        reasons.append("VOLATILITY_BASELINE_UNAVAILABLE")
    elif recent_average >= reference_average * 1.5:
        volatility = "ELEVATED"
    elif recent_average <= reference_average * 0.65:
        volatility = "LOW"
    else:
        volatility = "NORMAL"

    if structure in {"UPWARD_STRUCTURE", "DOWNWARD_STRUCTURE"}:
        market_regime = "TREND"
    elif structure == "MIXED_STRUCTURE":
        market_regime = "MIXED"
    else:
        market_regime = "UNAVAILABLE"
    return SessionRegimeReport(
        session_label=session,
        session_timezone_basis=timezone_basis,
        volatility_regime=volatility,
        market_regime=market_regime,
        spread_state=spread_state if spread_state in {"NORMAL", "ELEVATED"} else "UNAVAILABLE",
        observed_at_utc=observed_at,
        reason_codes=reasons,
    )


def _session_context(observed_at: datetime) -> tuple[str, str]:
    if observed_at.weekday() >= 5:
        return "WEEKEND", "IANA_MARKET_SESSION_TIMEZONES"
    try:
        london = observed_at.astimezone(ZoneInfo("Europe/London"))
        new_york = observed_at.astimezone(ZoneInfo("America/New_York"))
        asia = observed_at.astimezone(ZoneInfo("Asia/Tokyo"))
        timezone_basis = "IANA_MARKET_SESSION_TIMEZONES"
    except ZoneInfoNotFoundError:
        # Windows Python can be installed without the tzdata package. Use a
        # clearly-labelled UTC schedule rather than failing the entire worker.
        london = observed_at
        new_york = observed_at.replace(hour=(observed_at.hour - 5) % 24)
        asia = observed_at.replace(hour=(observed_at.hour + 9) % 24)
        timezone_basis = "UTC_APPROXIMATION_NO_TZDATA"
    london_open = 8 <= london.hour < 17
    new_york_open = 8 <= new_york.hour < 17
    if london_open and new_york_open:
        return "LONDON_NEW_YORK_OVERLAP", timezone_basis
    if london_open:
        return "LONDON", timezone_basis
    if new_york_open:
        return "NEW_YORK", timezone_basis
    if 8 <= asia.hour < 17:
        return "ASIA", timezone_basis
    return "OFF_HOURS", timezone_basis

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.analysis.professional import estimated_order_flow, opening_range, professional_research, volume_profile
from app.schemas.market import Candle, DataQualityReport, DataStatus, QuoteResponse


def bar(at: datetime, close: float, *, high: float | None = None, low: float | None = None, volume: int = 10) -> Candle:
    return Candle(
        open_time_utc=at, open=close - 0.25, high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5, close=close, tick_volume=volume, completed=True,
    )


def test_tick_proxy_profile_and_estimated_delta_never_claim_executed_futures_flow():
    start = datetime(2026, 10, 22, tzinfo=UTC)
    values = [bar(start + timedelta(minutes=5 * index), 4100 + (index % 2), volume=10 + index) for index in range(8)]

    profile = volume_profile(values, 0.01)
    flow = estimated_order_flow(values)

    assert profile.source_category.value == "BROKER_TICK_PROXY"
    assert profile.profile_basis == "COMPLETED_BAR_CLOSE_BUCKETED_BROKER_TICK_ACTIVITY"
    assert "CLOSE_BUCKET_PROXY_NOT_VOLUME_AT_PRICE" in profile.reason_codes
    assert flow.source_category.value == "ESTIMATED_DELTA"
    assert "NOT_GENUINE_FUTURES_ORDER_FLOW" in flow.reason_codes


def test_london_opening_range_uses_iana_local_session_and_completed_breakout():
    # London is still BST on 22 October 2026, therefore 08:00 London is 07:00 UTC.
    start = datetime(2026, 10, 22, 7, 0, tzinfo=UTC)
    values = [bar(start + timedelta(minutes=5 * index), 4100 + index, high=4101 + index, low=4099 + index) for index in range(6)]
    values.append(bar(start + timedelta(minutes=30), 4108, high=4109, low=4107, volume=30))

    result = opening_range(values)

    assert result.session == "LONDON"
    assert result.range_high == 4106
    assert result.state == "BREAKOUT"
    assert result.direction == "BULLISH"
    assert "IANA_SESSION_TIMEZONE" in result.reason_codes


def test_professional_research_blocks_paper_eligibility_when_costs_are_not_source_backed():
    start = datetime(2026, 10, 22, tzinfo=UTC)
    values = [bar(start + timedelta(minutes=5 * index), 4100 + index * 0.2, volume=20) for index in range(100)]
    quote = QuoteResponse(
        observed_at_utc=values[-1].open_time_utc + timedelta(minutes=5),
        source_timestamp_utc=values[-1].open_time_utc + timedelta(minutes=5),
        data_status=DataStatus.LIVE, symbol="XAUUSD", bid=4120, ask=4120.3,
        point=0.01, tick_size=0.01, tick_value=1.0, volume_min=0.01, volume_max=100,
        volume_step=0.01, contract_size=100, stops_level_points=0, freeze_level_points=0,
        tick_age_seconds=0.2, spread_points=30,
    )

    result = professional_research(values, quote, "UPCOMING_USD_EVENT")

    assert result.volume_source_category.value == "BROKER_TICK_PROXY"
    assert result.risk_engine.costs_complete is False
    assert result.risk_engine.lifecycle_state != "PAPER_ELIGIBLE"
    assert "NO_ORDER_EXECUTION" in result.risk_engine.reason_codes


def test_central_risk_governor_rejects_an_elevated_spread_integrity_condition():
    start = datetime(2026, 10, 22, tzinfo=UTC)
    values = [bar(start + timedelta(minutes=5 * index), 4100 + index * 0.2, volume=20) for index in range(100)]
    quote = QuoteResponse(
        observed_at_utc=values[-1].open_time_utc + timedelta(minutes=5),
        source_timestamp_utc=values[-1].open_time_utc + timedelta(minutes=5),
        data_status=DataStatus.LIVE, symbol="XAUUSD", bid=4120, ask=4120.3,
        point=0.01, tick_size=0.01, tick_value=1.0, volume_min=0.01, volume_max=100,
        volume_step=0.01, contract_size=100, tick_age_seconds=0.2, spread_points=30,
    )
    quality = DataQualityReport(
        status="WATCH", quote_status=DataStatus.LIVE, tick_age_seconds=0.2,
        spread_points=30, spread_baseline_points=10, spread_state="ELEVATED",
        checked_at_utc=quote.observed_at_utc, reason_codes=["SPREAD_ELEVATED"],
    )

    result = professional_research(values, quote, "UPCOMING_USD_EVENT", data_quality=quality)

    assert result.risk_engine.state == "REJECTED"
    assert result.risk_engine.lifecycle_state == "REJECTED"
    assert "ELEVATED_SPREAD_GATE" in result.risk_engine.reason_codes

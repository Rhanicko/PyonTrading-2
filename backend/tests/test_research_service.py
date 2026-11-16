from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.schemas.market import CalendarEvent, Candle, DataStatus, EventsResponse, QuoteResponse
from app.services.research import ResearchCoordinator
from app.storage.database import write_strategy_setting, write_operation_control


class FakeAdapter:
    def __init__(self, candles: list[Candle] | dict[str, list[Candle]]) -> None:
        self.candles_by_timeframe = candles if isinstance(candles, dict) else {
            "M5": candles, "M15": candles, "H1": candles, "H4": candles,
        }
        self.requested_timeframes: list[str] = []
        self.requested_limits: list[tuple[str, int]] = []

    def candles(self, _symbol, timeframe, limit):
        self.requested_timeframes.append(timeframe)
        self.requested_limits.append((timeframe, limit))
        return DataStatus.LIVE, [], self.candles_by_timeframe.get(timeframe, [])

    def quote(self, symbol):
        return QuoteResponse(
            observed_at_utc=datetime.now(UTC), source_timestamp_utc=datetime.now(UTC),
            data_status=DataStatus.LIVE, symbol=symbol, bid=4200, ask=4200.3,
            point=0.01, tick_size=0.01, tick_value=1.0, contract_size=100,
            volume_min=0.01, volume_max=100, volume_step=0.01,
            tick_age_seconds=0.2, spread_points=30,
        )


class FakeCalendar:
    def upcoming_usd_events(self):
        return EventsResponse(
            observed_at_utc=datetime.now(UTC),
            source_timestamp_utc=datetime.now(UTC),
            data_status=DataStatus.LIVE,
            source_url="https://example.test/calendar",
        )


def test_closed_quote_does_not_mark_archived_research_as_live(tmp_path: Path):
    class ClosedQuoteAdapter(FakeAdapter):
        def quote(self, symbol):
            return super().quote(symbol).model_copy(update={"data_status": DataStatus.MARKET_CLOSED})

    result = ResearchCoordinator(
        ClosedQuoteAdapter(fresh_multi_timeframe_candles()), FakeCalendar(), tmp_path / "research.db"
    ).snapshot("XAUUSD")

    assert result.analysis_timeframes[0].data_status == DataStatus.LIVE
    assert result.data_status == DataStatus.MARKET_CLOSED
    assert result.market_state == "DATA UNAVAILABLE"
    assert result.live_research_watch is not None
    assert result.live_research_watch.data_status == DataStatus.MARKET_CLOSED
    assert result.live_research_watch.lifecycle == "UNAVAILABLE"


@pytest.mark.parametrize("change,reason", [
    ("stale", "STALE_COMPLETED_TIMEFRAME"),
    ("future", "FUTURE_COMPLETED_TIMEFRAME"),
    ("duplicate", "DUPLICATE_OR_UNORDERED_TIMEFRAME"),
])
def test_research_rejects_invalid_timeframe_timing_even_with_live_quote(tmp_path, change, reason):
    candles = fresh_multi_timeframe_candles()
    if change == "stale":
        candles["M15"] = [bar.model_copy(update={"open_time_utc": bar.open_time_utc - timedelta(days=2)}) for bar in candles["M15"]]
    elif change == "future":
        candles["M15"] = [bar.model_copy(update={"open_time_utc": bar.open_time_utc + timedelta(hours=1)}) for bar in candles["M15"]]
    else:
        candles["M15"][-3] = candles["M15"][-2]
    result = ResearchCoordinator(FakeAdapter(candles), FakeCalendar(), tmp_path / "research.db").snapshot("XAUUSD")
    evidence = next(item for item in result.analysis_timeframes if item.timeframe == "M15")
    assert evidence.data_status != DataStatus.LIVE
    assert reason in evidence.reason_codes
    assert result.live_research_watch.signal_proof.publication_state == "WITHHELD"


def test_prior_session_context_retains_its_timestamp_when_current_broker_bar_is_present(tmp_path):
    candles = fresh_multi_timeframe_candles()
    candles["H4"] = [
        bar.model_copy(update={"open_time_utc": bar.open_time_utc - timedelta(days=2)}) if bar.completed else bar
        for bar in candles["H4"]
    ]
    result = ResearchCoordinator(FakeAdapter(candles), FakeCalendar(), tmp_path / "research.db").snapshot("XAUUSD")
    h4 = next(item for item in result.analysis_timeframes if item.timeframe == "H4")
    assert h4.data_status == DataStatus.LIVE
    assert h4.source_timestamp_utc == candles["H4"][-2].open_time_utc + timedelta(hours=4)
    assert "PRIOR_BROKER_SESSION_CONTEXT" in h4.reason_codes


class EventCalendar:
    def __init__(self, event: CalendarEvent) -> None:
        self.event = event

    def upcoming_usd_events(self):
        now = datetime.now(UTC)
        return EventsResponse(
            observed_at_utc=now,
            source_timestamp_utc=now,
            data_status=DataStatus.LIVE,
            source_url="https://example.test/calendar",
            events=[self.event],
        )


TIMEFRAME_MINUTES = {"M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440, "M1": 1}
TIMEFRAME_EVIDENCE_WINDOWS = {"M5": 144, "M15": 96, "H1": 72, "H4": 60, "D1": 60, "M1": 60}
INDICATOR_WARMUP_BARS = 180
TIMEFRAME_WINDOWS = {
    timeframe: required_completed + INDICATOR_WARMUP_BARS + 1
    for timeframe, required_completed in TIMEFRAME_EVIDENCE_WINDOWS.items()
}


def trend_candles(timeframe: str, direction: int = 1) -> list[Candle]:
    step = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    count = TIMEFRAME_WINDOWS[timeframe]
    start = datetime.now(UTC).replace(second=0, microsecond=0) - step * (count - 1)
    values = []
    for index in range(count):
        open_price = 4200 + (direction * index)
        close_price = open_price + (direction * 0.8)
        values.append(Candle(
            open_time_utc=start + (step * index),
            open=open_price,
            high=max(open_price, close_price) + 1,
            low=min(open_price, close_price) - 1,
            close=close_price,
            tick_volume=10,
            completed=index < count - 1,
        ))
    return values


def multi_timeframe_candles(direction: int = 1) -> dict[str, list[Candle]]:
    return {timeframe: trend_candles(timeframe, direction) for timeframe in TIMEFRAME_MINUTES}


def fresh_multi_timeframe_candles(direction: int = 1) -> dict[str, list[Candle]]:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    values_by_timeframe: dict[str, list[Candle]] = {}
    for timeframe, minutes in TIMEFRAME_MINUTES.items():
        count = TIMEFRAME_WINDOWS[timeframe]
        step = timedelta(minutes=minutes)
        start = now - step * (count - 1)
        candles: list[Candle] = []
        for index in range(count):
            open_price = 4200 + direction * index
            close_price = open_price + direction * 0.8
            candles.append(Candle(
                open_time_utc=start + step * index,
                open=open_price,
                high=max(open_price, close_price) + 1,
                low=min(open_price, close_price) - 1,
                close=close_price,
                tick_volume=10,
                completed=index < count - 1,
            ))
        values_by_timeframe[timeframe] = candles
    return values_by_timeframe


def test_top_down_validation_separates_bias_setup_trigger_and_optional_timing(tmp_path):
    result = ResearchCoordinator(FakeAdapter(fresh_multi_timeframe_candles()), FakeCalendar(), tmp_path / "research.db").snapshot("XAUUSD")
    assert result.top_down.direction == "LONG_CONTEXT"
    stages = {item.stage: item for item in result.top_down.stages}
    assert stages["BIAS"].timeframes == ["D1", "H4"]
    assert stages["BIAS"].state == "CONFIRMED"
    assert stages["SETUP"].state == "CONFIRMED"
    assert stages["TRIGGER"].state == "CONFIRMED"
    assert stages["TIMING"].required is False
    assert stages["SETUP"].invalidation_price is not None
    assert all(item.source_timestamp_utc <= result.observed_at_utc for item in result.top_down.timeframes)


def test_fast_timeframe_cannot_override_opposing_daily_bias(tmp_path):
    candles = fresh_multi_timeframe_candles()
    candles["D1"] = fresh_multi_timeframe_candles(-1)["D1"]
    candles["M5"] = [bar.model_copy(update={"spread_points": 30}) for bar in candles["M5"]]

    class NearbyQuote(FakeAdapter):
        def quote(self, symbol):
            close = candles["M5"][-2].close
            return super().quote(symbol).model_copy(update={"bid": close, "ask": close + 0.3})

    coordinator = ResearchCoordinator(NearbyQuote(candles), FakeCalendar(), tmp_path / "research.db")
    result = coordinator.snapshot("XAUUSD")
    assert next(item for item in result.top_down.stages if item.stage == "BIAS").state == "REJECTED"
    assert result.live_research_watch.signal_proof.publication_state == "WITHHELD"
    assert "TOP_DOWN_CONFIRMATION" in result.live_research_watch.signal_proof.reason_codes
    assert result.live_research_watch.reference_levels is None
    review = coordinator.analyze_market("XAUUSD")
    assert review.decision == "NO_TRADE"
    assert review.top_down.state == "REJECTED"


def test_missing_daily_history_is_explicit_and_optional_m1_does_not_replace_it(tmp_path):
    candles = fresh_multi_timeframe_candles()
    candles["D1"] = []
    result = ResearchCoordinator(FakeAdapter(candles), FakeCalendar(), tmp_path / "research.db").snapshot("XAUUSD")
    assert next(item for item in result.top_down.stages if item.stage == "BIAS").state == "UNAVAILABLE"
    assert result.top_down.state == "UNAVAILABLE"
    assert result.live_research_watch.signal_proof.publication_state == "WITHHELD"


def test_emergency_stop_withholds_qualified_research_publication(tmp_path):
    candles = fresh_multi_timeframe_candles()
    candles["M5"] = [bar.model_copy(update={"spread_points": 30}) for bar in candles["M5"]]

    class NearbyQuote(FakeAdapter):
        def quote(self, symbol):
            close = candles["M5"][-2].close
            return super().quote(symbol).model_copy(update={"bid": close, "ask": close + 0.3})

    database = tmp_path / "research.db"
    coordinator = ResearchCoordinator(NearbyQuote(candles), FakeCalendar(), database)
    assert coordinator.live_research_watch("XAUUSD").signal_proof.publication_state == "ELIGIBLE"
    write_operation_control(database, key="paper_kill_switch", value="true", actor="LOCAL_OPERATOR", action="STOP")
    watch = coordinator.live_research_watch("XAUUSD")
    assert watch.signal_proof.publication_state == "WITHHELD"
    assert watch.reference_levels is None
    assert watch.lifecycle == "WITHHELD"


def test_nearer_low_impact_event_does_not_hide_a_high_impact_release(tmp_path):
    now = datetime.now(UTC)
    events = [CalendarEvent(title=title, currency="USD", impact=impact,
                           event_time_utc=now + timedelta(minutes=minutes),
                           event_time_manila=now + timedelta(minutes=minutes), source_url="https://example.test/calendar")
              for title, impact, minutes in [("Minor release", "Low", 5), ("Major release", "High", 30)]]
    response = EventsResponse(observed_at_utc=now, source_timestamp_utc=now, data_status=DataStatus.LIVE,
                              source_url="https://example.test/calendar", events=events)
    result = ResearchCoordinator(FakeAdapter(fresh_multi_timeframe_candles()), FakeCalendar(), tmp_path / "research.db").snapshot("XAUUSD", calendar_response=response)
    assert result.event_risk_state == "HIGH_IMPACT_WINDOW"
    assert result.live_research_watch.signal_proof.publication_state == "WITHHELD"


def test_opposing_recent_structure_break_does_not_confirm_a_bullish_m15_setup(tmp_path, monkeypatch):
    from dataclasses import replace
    from app.analysis.technical import StructureEvent
    from app.services import research as research_module

    candles = fresh_multi_timeframe_candles()
    candles["M15"][-2] = candles["M15"][-2].model_copy(update={"close": candles["M15"][-3].close - 0.1})
    original = research_module.analyze_completed_candles

    def opposing_break(window, duration):
        snapshot = original(window, duration)
        if duration == timedelta(minutes=15):
            anchor = window[-1].open_time_utc
            return replace(snapshot, structure_events=(StructureEvent(kind="CHOCH", direction="BEARISH", level=window[-1].close,
                           source_bar_time=anchor, confirmation_bar_time=anchor, detected_at=anchor + duration, known_at=anchor + duration),))
        return snapshot

    monkeypatch.setattr(research_module, "analyze_completed_candles", opposing_break)
    result = ResearchCoordinator(FakeAdapter(candles), FakeCalendar(), tmp_path / "research.db").snapshot("XAUUSD")
    stage = next(item for item in result.top_down.stages if item.stage == "SETUP")
    assert stage.state == "PENDING"


@pytest.mark.parametrize("direction", [1, -1])
def test_range_breakout_vote_abstains_without_a_completed_close_breakout(tmp_path: Path, direction: int):
    candles = fresh_multi_timeframe_candles(direction)
    m5 = candles["M5"]
    previous = m5[-3]
    last_completed = m5[-2]
    m5[-2] = last_completed.model_copy(update={
        "close": previous.close - direction * 0.2,
        "high": max(last_completed.high, previous.close),
    })
    result = ResearchCoordinator(
        FakeAdapter(candles), FakeCalendar(), tmp_path / "research.db"
    ).snapshot("XAUUSD")

    assert result.strategy_ensemble is not None
    breakout = next(
        vote for vote in result.strategy_ensemble.votes
        if vote.strategy_id == "RANGE_BREAKOUT"
    )
    assert breakout.decision == "ABSTAIN"
    assert "NO_COMPLETED_CLOSE_BREAKOUT" in breakout.reason_codes


def test_research_exposes_aligned_watch_condition_without_issuing_an_order(tmp_path: Path):
    candles = fresh_multi_timeframe_candles()
    adapter = FakeAdapter(candles)
    coordinator = ResearchCoordinator(adapter, FakeCalendar(), tmp_path / "research.db")

    result = coordinator.snapshot("XAUUSD")

    assert result.market_state == "WATCH LONG"
    assert result.research_window_hours == 12
    assert [bot.bot_id for bot in result.bots] == [
        "quality", "chart", "momentum", "calendar", "context", "liquidity", "volume", "order_flow", "risk", "postmortem", "strategy",
    ]
    chart_bot = next(bot for bot in result.bots if bot.bot_id == "chart")
    strategy_bot = next(bot for bot in result.bots if bot.bot_id == "strategy")
    assert chart_bot.state == "OBSERVING"
    assert chart_bot.label == "Chart analyst"
    assert chart_bot.facts[0].startswith("M5: Upward Structure")
    assert [evidence.timeframe for evidence in result.analysis_timeframes] == ["M5", "M15", "H1", "H4"]
    assert all(evidence.data_status == DataStatus.LIVE for evidence in result.analysis_timeframes)
    m5 = result.analysis_timeframes[0]
    assert m5.indicators is not None
    assert m5.indicators.ema_20 is not None
    assert m5.indicators.ema_60 is not None
    assert m5.indicators.rsi_14 is not None
    assert m5.indicators.atr_14 is not None
    assert m5.indicators.range_position_percent is not None
    assert m5.indicators.latest_structure_event is None or m5.indicators.latest_structure_event.startswith(("BULLISH", "BEARISH"))
    assert adapter.requested_timeframes == ["M5", "M15", "H1", "H4", "D1", "M1"]
    assert adapter.requested_limits == [("M5", 325), ("M15", 277), ("H1", 253), ("H4", 241), ("D1", 241), ("M1", 241)]
    assert "CONFIRMATION_TIMESTAMPS_RETAINED" in chart_bot.reason_codes
    assert "NOT_A_TRADE_SIGNAL" in chart_bot.reason_codes
    assert result.data_quality is not None
    assert result.data_quality.status == "CLEAR"
    assert result.event_risk_state == "NO_EVENT_IN_EXPORT"
    assert result.strategy_ensemble is not None
    assert result.strategy_ensemble.decision == "WATCH_LONG"
    assert result.live_research_watch is not None
    assert result.live_research_watch.analysis_timeframes == result.analysis_timeframes
    assert result.live_research_watch.evidence_score_basis == "EVIDENCE_COVERAGE_NOT_PROBABILITY"
    assert result.professional_analysis is not None
    assert result.professional_analysis.volume_momentum.source_category.value == "BROKER_TICK_PROXY"
    assert result.professional_analysis.estimated_order_flow.source_category.value == "ESTIMATED_DELTA"
    assert result.professional_analysis.market_depth.source_category.value == "UNAVAILABLE"
    assert strategy_bot.state == "COLLECTING_EVIDENCE"
    assert "NO_CONFIDENCE_SCORE" in strategy_bot.reason_codes
    assert result.evidence_observations == 1


def test_research_blocks_chart_bot_when_twelve_hour_window_is_incomplete(tmp_path: Path):
    candle = Candle(
        open_time_utc=datetime(2026, 10, 21, tzinfo=UTC), open=4100, high=4101,
        low=4099, close=4100.5, tick_volume=10, completed=False,
    )
    coordinator = ResearchCoordinator(FakeAdapter([candle]), FakeCalendar(), tmp_path / "research.db")

    result = coordinator.snapshot("XAUUSD")

    assert result.market_state == "DATA UNAVAILABLE"
    assert next(bot for bot in result.bots if bot.bot_id == "chart").state == "BLOCKED"
    assert next(bot for bot in result.bots if bot.bot_id == "strategy").state == "BLOCKED"


def test_live_research_snapshot_does_not_persist_duplicate_evidence(tmp_path: Path):
    coordinator = ResearchCoordinator(
        FakeAdapter(fresh_multi_timeframe_candles()), FakeCalendar(), tmp_path / "research.db"
    )

    result = coordinator.snapshot("XAUUSD", persist_evidence=False)

    assert result.evidence_observations == 0
    assert result.live_research_watch is not None
    assert result.live_research_watch.lifecycle == "ACTIVE_RESEARCH_WATCH"


def test_research_marks_a_near_high_impact_event_as_elevated_context(tmp_path: Path):
    now = datetime.now(UTC)
    event = CalendarEvent(
        title="Test high-impact release",
        currency="USD",
        impact="High",
        event_time_utc=now + timedelta(minutes=45),
        event_time_manila=now + timedelta(minutes=45),
        source_url="https://example.test/calendar",
    )
    candles = [
        Candle(
            open_time_utc=now - timedelta(minutes=5 * (145 - index)), open=4100 + index,
            high=4101 + index, low=4099 + index, close=4100.5 + index,
            tick_volume=10, completed=index < 144,
        )
        for index in range(145)
    ]

    result = ResearchCoordinator(FakeAdapter(candles), EventCalendar(event), tmp_path / "research.db").snapshot("XAUUSD")

    news = next(bot for bot in result.bots if bot.bot_id == "calendar")
    assert "high-impact event is within two hours" in news.summary
    assert news.facts[0] == "Risk horizon: High-impact event is within two hours"
    assert "Public-calendar values are informational" in news.facts[2]


def test_market_screen_returns_watch_long_only_when_strict_gates_align(tmp_path: Path):
    result = ResearchCoordinator(
        FakeAdapter(multi_timeframe_candles()), FakeCalendar(), tmp_path / "research.db"
    ).analyze_market("XAUUSD")

    assert result.decision == "WATCH_LONG"
    assert result.market_context == "UPWARD_STRUCTURE"
    assert all(gate["state"] == "PASS" for gate in result.gates)
    assert [evidence.structure for evidence in result.analysis_timeframes] == ["UPWARD_STRUCTURE"] * 4
    assert result.analysis_mode == "RESEARCH_SCREEN_V5_SHARED_TOP_DOWN"
    assert "UNVALIDATED_RESEARCH_SIGNAL" in result.reason_codes
    assert "NO_ORDER_EXECUTION" in result.reason_codes


def test_market_screen_preserves_gap_context_but_withholds_an_unconfirmed_top_down_review(tmp_path: Path):
    candles = multi_timeframe_candles()
    m5 = candles["M5"]
    delay = timedelta(minutes=10)
    candles["M5"] = [
        candle.model_copy(update={"open_time_utc": candle.open_time_utc - delay}) if index < INDICATOR_WARMUP_BARS + 40 else candle
        for index, candle in enumerate(m5)
    ]

    result = ResearchCoordinator(
        FakeAdapter(candles), FakeCalendar(), tmp_path / "research.db"
    ).analyze_market("XAUUSD")

    assert result.decision == "NO_TRADE"
    assert result.data_quality is not None
    assert result.data_quality.status == "WATCH"
    assert next(gate for gate in result.gates if gate["label"] == "Tick / candle integrity") == {
        "label": "Tick / candle integrity", "state": "WATCH", "reason": "WATCH",
    }
    assert next(gate for gate in result.gates if gate["label"] == "Central risk governor") == {
        "label": "Central risk governor", "state": "PASS", "reason": "REVIEW_REQUIRED",
    }
    assert result.strategy_ensemble is not None
    assert "DATA_QUALITY_WATCH_NON_BLOCKING" in result.strategy_ensemble.reason_codes


def test_live_research_watch_is_automatic_and_expires_at_the_next_completed_m5_review(tmp_path: Path):
    watch = ResearchCoordinator(
        FakeAdapter(fresh_multi_timeframe_candles()), FakeCalendar(), tmp_path / "research.db"
    ).live_research_watch("XAUUSD")

    assert watch.lifecycle == "ACTIVE_RESEARCH_WATCH"
    assert watch.direction == "LONG_CONTEXT"
    assert watch.research_horizon == "MULTI_SESSION_CONTEXT"
    assert watch.horizon_basis == "M5_M15_H1_H4_COMPLETED_CANDLES_ALIGNED"
    assert watch.horizon_review_at_utc is not None
    assert "H4_CONTEXT_CONFIRMED" in watch.horizon_reason_codes
    assert watch.evidence_score == 100
    assert watch.active_from_utc is not None
    assert watch.scheduled_review_at_utc is not None
    assert watch.expires_at_utc == watch.scheduled_review_at_utc
    assert "EVIDENCE_SCORE_NOT_PROBABILITY" in watch.reason_codes
    assert "NO_ORDER_EXECUTION" in watch.reason_codes
    assert watch.reference_levels is None  # The fake quote is far from completed-candle prices.


def test_active_watch_exposes_source_backed_reference_levels_only_with_a_nearby_live_quote(tmp_path: Path):
    candles = fresh_multi_timeframe_candles()
    candles["M5"] = [candle.model_copy(update={"spread_points": 30}) for candle in candles["M5"]]

    class NearbyQuoteAdapter(FakeAdapter):
        def quote(self, symbol):
            quote = super().quote(symbol)
            close = candles["M5"][-2].close
            return quote.model_copy(update={"bid": close, "ask": close + 0.3})

    watch = ResearchCoordinator(
        NearbyQuoteAdapter(candles), FakeCalendar(), tmp_path / "research.db"
    ).live_research_watch("XAUUSD")

    assert watch.lifecycle == "ACTIVE_RESEARCH_WATCH"
    assert watch.reference_levels is not None
    levels = watch.reference_levels
    assert levels.entry == candles["M5"][-2].close + 0.3
    assert levels.stop_loss < levels.entry < levels.take_profit_1 < levels.take_profit_2
    assert levels.basis == "M5_ATR14_1R_2R_UNVALIDATED"
    assert levels.source_candle_close_utc == watch.active_from_utc
    assert watch.signal_proof is not None
    assert watch.signal_proof.publication_state == "ELIGIBLE"
    assert watch.signal_proof.performance_state == "UNVALIDATED"
    assert all(check.passed for check in watch.signal_proof.checks)
    assert {check.code for check in watch.signal_proof.checks} == {
        "FRESH_BROKER_QUOTE", "COMPLETED_MTF_ALIGNMENT", "DATA_QUALITY_CLEAR",
        "CALENDAR_RISK_CHECKED", "RULE_AGREEMENT_NO_OPPOSITION",
        "CENTRAL_RISK_GATE", "SOURCE_BACKED_LEVELS", "SPREAD_BUFFER_WITHIN_ATR",
        "COMPLETED_CLOSE_TRIGGER", "TOP_DOWN_CONFIRMATION", "OPERATIONS_ALLOW_PUBLICATION",
    }


def test_proof_audit_reports_completed_timeframe_alignment_even_when_votes_abstain(tmp_path: Path):
    database = tmp_path / "research.db"
    write_strategy_setting(database, symbol="XAUUSD", strategy_id="MOMENTUM_ALIGNMENT", enabled=False)
    write_strategy_setting(database, symbol="XAUUSD", strategy_id="RANGE_BREAKOUT", enabled=False)
    watch = ResearchCoordinator(
        FakeAdapter(fresh_multi_timeframe_candles()), FakeCalendar(), database,
    ).live_research_watch("XAUUSD")

    assert watch.lifecycle == "WITHHELD"
    assert watch.signal_proof is not None
    checks = {check.code: check.passed for check in watch.signal_proof.checks}
    assert checks["COMPLETED_MTF_ALIGNMENT"] is True
    assert checks["RULE_AGREEMENT_NO_OPPOSITION"] is False
    assert watch.signal_proof.publication_state == "WITHHELD"


def test_automatic_publication_waits_for_a_new_completed_m5_closing_extreme(tmp_path: Path):
    candles = fresh_multi_timeframe_candles()
    candles["M5"] = [candle.model_copy(update={"spread_points": 30}) for candle in candles["M5"]]
    previous_close = candles["M5"][-3].close
    candles["M5"][-2] = candles["M5"][-2].model_copy(update={"close": previous_close - 0.1})

    class UnconfirmedCloseAdapter(FakeAdapter):
        def quote(self, symbol):
            quote = super().quote(symbol)
            close = candles["M5"][-2].close
            return quote.model_copy(update={"bid": close, "ask": close + 0.3})

    watch = ResearchCoordinator(
        UnconfirmedCloseAdapter(candles), FakeCalendar(), tmp_path / "research.db"
    ).live_research_watch("XAUUSD")

    assert watch.lifecycle == "WITHHELD"
    assert watch.reference_levels is None
    assert watch.signal_proof is not None
    assert watch.signal_proof.publication_state == "WITHHELD"
    assert "COMPLETED_CLOSE_TRIGGER" in watch.signal_proof.reason_codes


def test_wide_spread_withholds_publication_even_when_directional_levels_exist(tmp_path: Path):
    candles = fresh_multi_timeframe_candles()
    candles["M5"] = [candle.model_copy(update={"spread_points": 100}) for candle in candles["M5"]]

    class WideSpreadAdapter(FakeAdapter):
        def quote(self, symbol):
            quote = super().quote(symbol)
            close = candles["M5"][-2].close
            return quote.model_copy(update={
                "bid": close - 0.5, "ask": close + 0.5, "spread_points": 100,
            })

    watch = ResearchCoordinator(
        WideSpreadAdapter(candles), FakeCalendar(), tmp_path / "research.db"
    ).live_research_watch("XAUUSD")

    assert watch.lifecycle == "ACTIVE_RESEARCH_WATCH"
    assert watch.reference_levels is not None
    assert watch.signal_proof is not None
    assert watch.signal_proof.publication_state == "WITHHELD"
    assert "SPREAD_BUFFER_WITHIN_ATR" in watch.signal_proof.reason_codes


def test_short_watch_reference_levels_descend_and_stale_quote_has_no_levels(tmp_path: Path):
    candles = fresh_multi_timeframe_candles(direction=-1)

    class NearbyQuoteAdapter(FakeAdapter):
        def __init__(self, *, stale: bool) -> None:
            super().__init__(candles)
            self.stale = stale

        def quote(self, symbol):
            quote = super().quote(symbol)
            close = candles["M5"][-2].close
            return quote.model_copy(update={
                "bid": close, "ask": close + 0.3,
                "tick_age_seconds": 10 if self.stale else 0.2,
            })

    fresh = ResearchCoordinator(
        NearbyQuoteAdapter(stale=False), FakeCalendar(), tmp_path / "fresh.db"
    ).live_research_watch("XAUUSD")
    assert fresh.lifecycle == "ACTIVE_RESEARCH_WATCH"
    assert fresh.reference_levels is not None
    assert fresh.reference_levels.stop_loss > fresh.reference_levels.entry > fresh.reference_levels.take_profit_1 > fresh.reference_levels.take_profit_2

    stale = ResearchCoordinator(
        NearbyQuoteAdapter(stale=True), FakeCalendar(), tmp_path / "stale.db"
    ).live_research_watch("XAUUSD")
    assert stale.reference_levels is None
    assert stale.signal_proof is not None
    assert stale.signal_proof.publication_state == "WITHHELD"
    assert "FRESH_BROKER_QUOTE" in stale.signal_proof.reason_codes


def test_reference_levels_are_withheld_if_broker_tick_rounding_collapses_them(tmp_path: Path):
    candles = fresh_multi_timeframe_candles()

    class CoarseTickAdapter(FakeAdapter):
        def quote(self, symbol):
            quote = super().quote(symbol)
            close = candles["M5"][-2].close
            return quote.model_copy(update={"bid": close, "ask": close + 0.3, "tick_size": 100.0})

    watch = ResearchCoordinator(
        CoarseTickAdapter(candles), FakeCalendar(), tmp_path / "research.db"
    ).live_research_watch("XAUUSD")
    assert watch.lifecycle == "ACTIVE_RESEARCH_WATCH"
    assert watch.reference_levels is None


def test_withheld_watch_never_exposes_reference_levels(tmp_path: Path):
    now = datetime.now(UTC)
    event = CalendarEvent(
        title="Test high-impact release", currency="USD", impact="High",
        event_time_utc=now + timedelta(minutes=45), event_time_manila=now + timedelta(minutes=45),
        source_url="https://example.test/calendar",
    )
    watch = ResearchCoordinator(
        FakeAdapter(fresh_multi_timeframe_candles()), EventCalendar(event), tmp_path / "research.db"
    ).live_research_watch("XAUUSD")

    assert watch.lifecycle == "WITHHELD"
    assert watch.reference_levels is None


def test_live_research_horizon_is_unavailable_without_an_active_directional_watch(tmp_path: Path):
    now = datetime.now(UTC)
    event = CalendarEvent(
        title="Test high-impact release", currency="USD", impact="High",
        event_time_utc=now + timedelta(minutes=45), event_time_manila=now + timedelta(minutes=45),
        source_url="https://example.test/calendar",
    )
    watch = ResearchCoordinator(
        FakeAdapter(fresh_multi_timeframe_candles()), EventCalendar(event), tmp_path / "research.db"
    ).live_research_watch("XAUUSD")

    assert watch.lifecycle == "WITHHELD"
    assert watch.research_horizon == "UNAVAILABLE"
    assert watch.horizon_basis == "NO_ACTIVE_DIRECTIONAL_RESEARCH_WATCH"


def test_live_research_watch_is_withheld_when_event_risk_blocks_directional_research(tmp_path: Path):
    now = datetime.now(UTC)
    event = CalendarEvent(
        title="Test high-impact release", currency="USD", impact="High",
        event_time_utc=now + timedelta(minutes=45), event_time_manila=now + timedelta(minutes=45),
        source_url="https://example.test/calendar",
    )
    watch = ResearchCoordinator(
        FakeAdapter(fresh_multi_timeframe_candles()), EventCalendar(event), tmp_path / "research.db"
    ).live_research_watch("XAUUSD")

    assert watch.lifecycle == "WITHHELD"
    assert watch.direction == "NONE"
    assert watch.event_risk_state == "HIGH_IMPACT_WINDOW"
    assert any("Event-risk horizon" in item for item in watch.invalidation_conditions)


def test_market_screen_vetoes_watch_when_high_impact_event_is_near(tmp_path: Path):
    now = datetime.now(UTC)
    event = CalendarEvent(
        title="Test high-impact release", currency="USD", impact="High",
        event_time_utc=now + timedelta(minutes=45), event_time_manila=now + timedelta(minutes=45),
        source_url="https://example.test/calendar",
    )
    candles = [
        Candle(
            open_time_utc=now - timedelta(minutes=5 * (145 - index)), open=4100 + index,
            high=4101 + index, low=4099 + index, close=4100.8 + index,
            tick_volume=10, completed=index < 144,
        )
        for index in range(145)
    ]
    result = ResearchCoordinator(FakeAdapter(candles), EventCalendar(event), tmp_path / "research.db").analyze_market("XAUUSD")

    assert result.decision == "NO_TRADE"
    assert next(gate for gate in result.gates if gate["label"] == "Event-risk horizon") == {
        "label": "Event-risk horizon", "state": "BLOCK", "reason": "HIGH_IMPACT_WINDOW",
    }


def test_market_screen_vetoes_directional_watch_when_timeframes_disagree(tmp_path: Path):
    candles = multi_timeframe_candles()
    candles["H1"] = trend_candles("H1", direction=-1)

    result = ResearchCoordinator(
        FakeAdapter(candles), FakeCalendar(), tmp_path / "research.db"
    ).analyze_market("XAUUSD")

    assert result.decision == "NO_TRADE"
    assert result.market_context == "MIXED_STRUCTURE"
    assert result.gates[2] == {
        "label": "Completed M5 / M15 / H1 / H4 evidence",
        "state": "PASS",
        "reason": "MULTI_TIMEFRAME_COMPLETED",
    }
    assert next(evidence for evidence in result.analysis_timeframes if evidence.timeframe == "H1").structure == "DOWNWARD_STRUCTURE"


def test_local_strategy_configuration_can_only_reduce_ensemble_eligibility(tmp_path: Path):
    database = tmp_path / "research.db"
    write_strategy_setting(database, symbol="XAUUSD", strategy_id="MOMENTUM_ALIGNMENT", enabled=False)
    write_strategy_setting(database, symbol="XAUUSD", strategy_id="RANGE_BREAKOUT", enabled=False)

    result = ResearchCoordinator(
        FakeAdapter(multi_timeframe_candles()), FakeCalendar(), database,
    ).analyze_market("XAUUSD")

    assert result.decision == "NO_TRADE"
    assert result.strategy_ensemble is not None
    disabled = [
        vote for vote in result.strategy_ensemble.votes
        if vote.strategy_id in {"MOMENTUM_ALIGNMENT", "RANGE_BREAKOUT"}
    ]
    assert all(vote.decision == "ABSTAIN" for vote in disabled)
    assert all("STRATEGY_DISABLED_BY_LOCAL_OWNER" in vote.reason_codes for vote in disabled)
    assert "LOCAL_STRATEGY_CONFIGURATION_APPLIED" in result.strategy_ensemble.reason_codes

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas.market import CalendarEvent, Candle, DataStatus, EventsResponse, QuoteResponse
from app.services.research import ResearchCoordinator
from app.storage.database import write_strategy_setting


class FakeAdapter:
    def __init__(self, candles: list[Candle] | dict[str, list[Candle]]) -> None:
        self.candles_by_timeframe = candles if isinstance(candles, dict) else {
            "M5": candles, "M15": candles, "H1": candles, "H4": candles,
        }
        self.requested_timeframes: list[str] = []

    def candles(self, _symbol, timeframe, _limit):
        self.requested_timeframes.append(timeframe)
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


TIMEFRAME_MINUTES = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}
TIMEFRAME_WINDOWS = {"M5": 145, "M15": 97, "H1": 73, "H4": 61}


def trend_candles(timeframe: str, direction: int = 1) -> list[Candle]:
    start = datetime(2026, 10, 10, 0, 0, tzinfo=UTC)
    step = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    count = TIMEFRAME_WINDOWS[timeframe]
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


def test_research_exposes_aligned_watch_condition_without_issuing_an_order(tmp_path: Path):
    start = datetime(2026, 10, 21, 0, 0, tzinfo=UTC)
    candles = [
        Candle(
            open_time_utc=start + timedelta(minutes=5 * index), open=4100 + index,
            high=4101 + index, low=4099 + index, close=4100.5 + index,
            tick_volume=10, completed=index < 144,
        )
        for index in range(145)
    ]
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
    assert adapter.requested_timeframes == ["M5", "M15", "H1", "H4"]
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
    assert result.analysis_mode == "RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES"
    assert "UNVALIDATED_RESEARCH_SIGNAL" in result.reason_codes
    assert "NO_ORDER_EXECUTION" in result.reason_codes


def test_market_screen_keeps_a_watch_when_an_older_candle_gap_is_non_blocking(tmp_path: Path):
    candles = multi_timeframe_candles()
    m5 = candles["M5"]
    delay = timedelta(minutes=10)
    candles["M5"] = [
        candle.model_copy(update={"open_time_utc": candle.open_time_utc + delay}) if index >= 40 else candle
        for index, candle in enumerate(m5)
    ]

    result = ResearchCoordinator(
        FakeAdapter(candles), FakeCalendar(), tmp_path / "research.db"
    ).analyze_market("XAUUSD")

    assert result.decision == "WATCH_LONG"
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
    assert "entry" not in watch.model_dump()
    assert "target" not in watch.model_dump()


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

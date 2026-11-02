import sqlite3
from datetime import UTC, datetime, timedelta

from app.schemas.market import Candle, ConnectionResponse, DataStatus, EventsResponse, QuoteResponse
from app.services.pipeline import M5_HISTORY_BOOTSTRAP_LIMIT, ResearchPipeline
from app.services.research import ResearchCoordinator
from app.storage.database import count_completed_candles, read_pipeline_summary



TIMEFRAME_MINUTES = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}
TIMEFRAME_COUNTS = {"M5": 145, "M15": 97, "H1": 73, "H4": 61}


def multi_timeframe_candles():
    start = datetime(2026, 10, 10, tzinfo=UTC)
    values = {}
    for timeframe, minutes in TIMEFRAME_MINUTES.items():
        candles = []
        for index in range(TIMEFRAME_COUNTS[timeframe]):
            open_price = 4200 + index
            close_price = open_price + 0.8
            candles.append(Candle(
                open_time_utc=start + timedelta(minutes=minutes * index),
                open=open_price,
                high=close_price + 1,
                low=open_price - 1,
                close=close_price,
                tick_volume=10,
                completed=index < TIMEFRAME_COUNTS[timeframe] - 1,
            ))
        values[timeframe] = candles
    return values


class PipelineAdapter:
    def __init__(self) -> None:
        self.candles_by_timeframe = multi_timeframe_candles()
        self.candle_requests: list[tuple[str, int]] = []

    def connection(self, symbol):
        return ConnectionResponse(
            observed_at_utc=datetime.now(UTC),
            data_status=DataStatus.LIVE,
            terminal_connected=True,
            configured_symbol=symbol,
            broker_server="MetaQuotes-Demo",
        )

    def candles(self, _symbol, timeframe, _limit):
        self.candle_requests.append((timeframe, _limit))
        return DataStatus.LIVE, [], self.candles_by_timeframe[timeframe]

    def quote(self, symbol):
        return QuoteResponse(
            observed_at_utc=datetime.now(UTC),
            source_timestamp_utc=datetime.now(UTC),
            data_status=DataStatus.LIVE,
            symbol=symbol,
            bid=4200.0,
            ask=4200.3,
            point=0.01,
        )


class PipelineCalendar:
    def upcoming_usd_events(self):
        now = datetime.now(UTC)
        return EventsResponse(
            observed_at_utc=now,
            source_timestamp_utc=now,
            data_status=DataStatus.LIVE,
            source_url="https://example.test/calendar",
            events=[],
        )


def test_pipeline_persists_completed_source_data_and_runs_research_without_http(tmp_path):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    calendar = PipelineCalendar()
    coordinator = ResearchCoordinator(adapter, calendar, database)
    pipeline = ResearchPipeline(adapter, calendar, coordinator, database, lambda: "XAUUSD")

    pipeline.run_once()

    assert count_completed_candles(
        database,
        symbol="XAUUSD",
        timeframe="M5",
        broker_server="MetaQuotes-Demo",
    ) == 144
    assert ("M5", M5_HISTORY_BOOTSTRAP_LIMIT) in adapter.candle_requests
    summary = read_pipeline_summary(database, symbol="XAUUSD")
    assert summary["jobs"] == {"COMPLETED": 1}
    assert summary["latest_run"] is not None
    assert summary["latest_run"]["data_status"] == "LIVE"
    assert summary["latest_model"] is not None
    assert summary["latest_model"]["state"] == "INSUFFICIENT_DATA"
    with sqlite3.connect(database) as connection:
        frozen_event_risk = connection.execute(
            "SELECT event_risk_state FROM frozen_research_decisions"
        ).fetchall()
        strategy_events = connection.execute(
            "SELECT strategy_id, disposition FROM strategy_journal_events ORDER BY strategy_id"
        ).fetchall()
        paper_statuses = connection.execute(
            "SELECT paper_status FROM frozen_research_decisions"
        ).fetchall()
    assert frozen_event_risk == [("NO_EVENT_IN_EXPORT",)]
    assert len(strategy_events) == 7
    assert {event[0] for event in strategy_events} == {
        "LIQUIDITY_SWEEP_REVERSAL",
        "ESTIMATED_ORDER_FLOW",
        "MARKET_DEPTH",
        "OPENING_RANGE_BREAKOUT",
        "VOLUME_PROFILE_AUCTION",
        "VWAP_VOLUME_MOMENTUM",
        "CROSS_MARKET_CONTEXT",
    }
    assert {event[1] for event in strategy_events} <= {"DATA_UNAVAILABLE", "REJECTED", "REVIEW_REQUIRED"}
    assert paper_statuses == [("NOT_CREATED",)]


def test_pipeline_labels_a_run_only_after_real_future_completed_bars(tmp_path):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    calendar = PipelineCalendar()
    coordinator = ResearchCoordinator(adapter, calendar, database)
    pipeline = ResearchPipeline(adapter, calendar, coordinator, database, lambda: "XAUUSD")

    pipeline.run_once()
    original = adapter.candles_by_timeframe["M5"]
    extension_start = original[-1].open_time_utc
    extension = []
    for index in range(13):
        base = 4400 + index
        extension.append(original[-1].model_copy(update={
            "open_time_utc": extension_start + timedelta(minutes=(index + 1) * 5),
            "open": base,
            "high": base + 1,
            "low": base - 1,
            "close": base + 0.5,
            "completed": index < 12,
        }))
    adapter.candles_by_timeframe["M5"] = original[:-1] + extension
    pipeline.run_once()

    with sqlite3.connect(database) as connection:
        labels = connection.execute("SELECT direction, horizon_bars FROM research_labels").fetchall()
    assert labels == [("UP", 12)]

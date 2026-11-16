import asyncio
import sqlite3
import time
from datetime import UTC, datetime, timedelta

from app.schemas.market import Candle, ConnectionResponse, DataStatus, EventsResponse, QuoteResponse
from app.services import pipeline as pipeline_module
from app.services.pipeline import M5_HISTORY_BOOTSTRAP_LIMIT, ResearchPipeline
from app.services.research import ResearchCoordinator
from app.storage.database import count_completed_candles, enqueue_research_job, read_pipeline_summary, read_recent_signal_history, read_validation_summary, record_frozen_research_decision, record_research_run, record_signal_history, store_completed_candles, write_operation_control



TIMEFRAME_MINUTES = {"M5": 5, "M15": 15, "H1": 60, "H4": 240, "D1": 1440, "M1": 1}
TIMEFRAME_COUNTS = {"M5": 325, "M15": 277, "H1": 253, "H4": 241, "D1": 241, "M1": 241}


def multi_timeframe_candles():
    values = {}
    for timeframe, minutes in TIMEFRAME_MINUTES.items():
        start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=minutes * (TIMEFRAME_COUNTS[timeframe] - 1))
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


def test_closed_market_labels_archived_contiguous_paper_candidates_without_new_research(tmp_path):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    candles = adapter.candles_by_timeframe["M5"][:13]
    anchor = candles[0].open_time_utc
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD", timeframe="M5",
        candles=candles, timeframe_seconds=300, observed_at_utc=anchor + timedelta(hours=2),
    )
    record_frozen_research_decision(
        database, decision_id="closed-paper", observed_at_utc=anchor, symbol="XAUUSD", anchor_time_utc=anchor,
        decision="WATCH_LONG", feature_set_version="research-v3", input_fingerprint="d" * 64,
        quote_source_timestamp_utc=anchor, quote_bid=4200, quote_ask=4200.3, spread_points=30,
        data_quality_state="CLEAR", event_risk_state="NO_EVENT_IN_EXPORT", session_regime="TREND",
        model_promotion_state="REVIEW_REQUIRED", paper_status="RECORDED", feature_snapshot={}, ensemble={},
        costs={"spread_points": 30, "commission_points": None, "slippage_points": None},
        reason_codes=["NO_ORDER_EXECUTION"],
    )
    live_quote = adapter.quote("XAUUSD")
    adapter.quote = lambda _symbol: live_quote.model_copy(update={"data_status": DataStatus.MARKET_CLOSED})
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")

    pipeline.run_once()

    assert read_validation_summary(database, symbol="XAUUSD")["labelled_candidates"] == 1
    assert read_pipeline_summary(database, symbol="XAUUSD")["latest_run"] is None


def test_closed_market_calibration_keeps_available_broker_point_metadata(tmp_path, monkeypatch):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    live_quote = adapter.quote("XAUUSD")
    adapter.quote = lambda _symbol: live_quote.model_copy(update={"data_status": DataStatus.MARKET_CLOSED})
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")

    def calibration_status(_candles, point):
        return [], ("POINT_VALUE_UNAVAILABLE",) if point is None else ("TRAINING_HISTORY_INSUFFICIENT",)

    monkeypatch.setattr(pipeline_module, "calibrate_strategies", calibration_status)
    pipeline.run_once()

    model = read_pipeline_summary(database, symbol="XAUUSD")["latest_model"]
    assert model["reason_codes"] == ["TRAINING_HISTORY_INSUFFICIENT"]


def test_walk_forward_timestamps_are_serializable_in_the_model_registry(tmp_path, monkeypatch):
    from app.analysis.training import Metrics, RollingValidationFold, StrategyCalibration

    now = datetime.now(UTC)
    metrics = Metrics(10, 6, 4, 10.0, 8.0)
    calibration = StrategyCalibration(
        strategy_id="PRICE_STRUCTURE_BASELINE", strategy_version="v1", selected_hold_bars=3,
        training=metrics, validation=metrics, held_out=metrics, state="REVIEW_REQUIRED", reason_codes=("NO_MODEL_PROMOTION",),
        walk_forward=(RollingValidationFold(training_candles=2000, validation_start_utc=now, validation_end_utc=now + timedelta(hours=1), selected_hold_bars=3, validation=metrics),),
    )
    monkeypatch.setattr(pipeline_module, "calibrate_strategies", lambda candles, point: ([calibration], ("NO_MODEL_PROMOTION",)))
    database = tmp_path / "research.db"
    adapter, calendar = PipelineAdapter(), PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")
    pipeline.run_once()
    assert read_pipeline_summary(database, symbol="XAUUSD")["latest_model"]["state"] == "REVIEW_REQUIRED"
    with sqlite3.connect(database) as connection:
        import json
        payload = json.loads(connection.execute("SELECT payload_json FROM model_versions").fetchone()[0])
    assert payload["calibrations"][0]["walk_forward"][0]["validation_start_utc"].startswith(now.date().isoformat())


def test_failed_calibration_persistence_is_retried_before_next_six_hour_interval(tmp_path, monkeypatch):
    import pytest

    database = tmp_path / "research.db"
    adapter, calendar = PipelineAdapter(), PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")
    original = pipeline_module.record_model_version
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary registry failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "record_model_version", fail_once)
    with pytest.raises(RuntimeError):
        pipeline.run_once()
    pipeline.run_once()
    assert read_pipeline_summary(database, symbol="XAUUSD")["latest_model"] is not None


def test_slow_optional_macro_refresh_does_not_delay_a_completed_bar_decision(tmp_path):
    from threading import Event

    release = Event()

    class SlowMacro:
        finished = False

        def refresh_if_due(self):
            release.wait(timeout=5)
            self.finished = True
            return []

        def snapshot(self):
            return []

    database = tmp_path / "research.db"
    adapter, calendar, macro = PipelineAdapter(), PipelineCalendar(), SlowMacro()
    coordinator = ResearchCoordinator(adapter, calendar, database, macro)
    pipeline = ResearchPipeline(adapter, calendar, coordinator, database, lambda: "XAUUSD", macro)
    try:
        pipeline.run_once()
        assert read_pipeline_summary(database, symbol="XAUUSD")["latest_run"] is not None
        assert not macro.finished, "An optional network source held up completed-bar research"
    finally:
        release.set()
        asyncio.run(pipeline.stop())


def test_new_completed_bar_wakes_research_before_the_idle_poll_interval(tmp_path):
    adapter, calendar = PipelineAdapter(), PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, tmp_path / "research.db"), tmp_path / "research.db", lambda: "XAUUSD")

    async def exercise():
        ran = asyncio.Event()
        cycles = 0

        async def cycle():
            nonlocal cycles
            cycles += 1
            ran.set()
            return True

        pipeline._run_cycle = cycle
        await pipeline.start()
        try:
            await asyncio.wait_for(ran.wait(), timeout=2)
            ran.clear()
            pipeline.notify_completed_bar("XAUUSD", adapter.candles_by_timeframe["M5"][-2])
            await asyncio.wait_for(ran.wait(), timeout=2)
            assert cycles >= 2
        finally:
            await pipeline.stop()

    asyncio.run(exercise())


def test_research_run_outcome_is_not_labelled_across_missing_m5_bars(tmp_path):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    contiguous = adapter.candles_by_timeframe["M5"][:14]
    candles = [*contiguous[:6], *contiguous[7:]]
    anchor = candles[0].open_time_utc
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD", timeframe="M5",
        candles=candles, timeframe_seconds=300, observed_at_utc=anchor + timedelta(hours=2),
    )
    record_research_run(
        database, run_id="gap-run", job_id="gap-job", observed_at_utc=anchor,
        symbol="XAUUSD", anchor_time_utc=anchor, trigger="COMPLETED_M5_BAR", data_status="LIVE",
        feature_set_version="mtf-research-v6", source_statuses={"timeframe_M5": "LIVE"},
        response={"market_state": "NO TRADE"}, reason_codes=[],
    )
    live_quote = adapter.quote("XAUUSD")
    adapter.quote = lambda _symbol: live_quote.model_copy(update={"data_status": DataStatus.MARKET_CLOSED})
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")

    pipeline.run_once()

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM research_labels WHERE run_id = 'gap-run'").fetchone()[0] == 0


def test_first_closed_cycle_backfills_paper_label_older_than_recent_six_thousand_bars(tmp_path):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    anchor = datetime(2026, 5, 18, tzinfo=UTC)
    candles = [Candle(
        open_time_utc=anchor + timedelta(minutes=5 * index), open=4100 + index * 0.01,
        high=4101 + index * 0.01, low=4099 + index * 0.01, close=4100.5 + index * 0.01,
        tick_volume=10, completed=True,
    ) for index in range(6_013)]
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD", timeframe="M5",
        candles=candles, timeframe_seconds=300, observed_at_utc=anchor + timedelta(days=30),
    )
    record_frozen_research_decision(
        database, decision_id="old-paper", observed_at_utc=anchor, symbol="XAUUSD", anchor_time_utc=anchor,
        decision="WATCH_LONG", feature_set_version="research-v3", input_fingerprint="e" * 64,
        quote_source_timestamp_utc=anchor, quote_bid=4100, quote_ask=4100.3, spread_points=30,
        data_quality_state="CLEAR", event_risk_state="NO_EVENT_IN_EXPORT", session_regime="TREND",
        model_promotion_state="REVIEW_REQUIRED", paper_status="RECORDED", feature_snapshot={}, ensemble={},
        costs={"spread_points": 30, "commission_points": None, "slippage_points": None},
        reason_codes=["NO_ORDER_EXECUTION"],
    )
    live_quote = adapter.quote("XAUUSD")
    adapter.quote = lambda _symbol: live_quote.model_copy(update={"data_status": DataStatus.MARKET_CLOSED})
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")

    pipeline.run_once()

    assert read_validation_summary(database, symbol="XAUUSD")["labelled_candidates"] == 1


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
    ) == 324
    assert ("M5", M5_HISTORY_BOOTSTRAP_LIMIT) in adapter.candle_requests
    summary = read_pipeline_summary(database, symbol="XAUUSD")
    assert summary["jobs"] == {"COMPLETED": 1}
    assert summary["latest_run"] is not None
    assert summary["latest_run"]["data_status"] == "LIVE"
    for timeframe in ("D1", "M1"):
        assert count_completed_candles(database, symbol="XAUUSD", timeframe=timeframe, broker_server="MetaQuotes-Demo") == 240
    assert summary["latest_model"] is not None
    assert summary["latest_model"]["state"] == "INSUFFICIENT_DATA"
    metrics = pipeline.status()["metrics"]
    assert metrics["pending_jobs"] == 0
    assert metrics["worker_failures"] == 0
    assert metrics["quote_latency_ms"] is not None
    assert metrics["m5_collection_latency_ms"] is not None
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


def test_pipeline_freezes_the_same_quote_used_for_its_research_decision(tmp_path):
    database = tmp_path / "research.db"

    class MovingQuoteAdapter(PipelineAdapter):
        def __init__(self):
            super().__init__()
            self.quote_reads = 0

        def quote(self, symbol):
            quote = super().quote(symbol)
            self.quote_reads += 1
            return quote.model_copy(update={"bid": 4200.0 + self.quote_reads, "ask": 4200.3 + self.quote_reads})

    adapter = MovingQuoteAdapter()
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")

    pipeline.run_once()

    with sqlite3.connect(database) as connection:
        frozen = connection.execute("SELECT quote_bid, quote_ask FROM frozen_research_decisions").fetchone()
    assert frozen == (4201.0, 4201.3)


def test_pipeline_status_exposes_missing_archived_decisions_even_after_latest_run_catches_up(tmp_path):
    database = tmp_path / "coverage.db"
    adapter = PipelineAdapter()
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")
    pipeline._broker_servers["XAUUSD"] = "MetaQuotes-Demo"
    first = datetime(2026, 10, 20, tzinfo=UTC)
    bars = [Candle(
        open_time_utc=first + timedelta(minutes=5 * index),
        open=4100.0, high=4101.0, low=4099.0, close=4100.5,
        tick_volume=10, completed=True,
    ) for index in range(4)]
    store_completed_candles(database, source="MT5", broker_server="MetaQuotes-Demo",
                            symbol="XAUUSD", timeframe="M5", candles=bars,
                            timeframe_seconds=300, observed_at_utc=first + timedelta(hours=1))
    store_completed_candles(database, source="MT5", broker_server="Other-Broker",
                            symbol="XAUUSD", timeframe="M5", candles=[bars[-1].model_copy(update={
                                "open_time_utc": first + timedelta(minutes=20),
                            })], timeframe_seconds=300, observed_at_utc=first + timedelta(hours=1))
    for index in (0, 3):
        record_research_run(
            database, run_id=f"run-{index}", job_id=f"job-{index}",
            observed_at_utc=first + timedelta(minutes=5 * index + 1),
            symbol="XAUUSD", anchor_time_utc=bars[index].open_time_utc,
            trigger="COMPLETED_M5_BAR", data_status="LIVE", feature_set_version="fixture-v1",
            source_statuses={"M5": "LIVE"}, response={}, reason_codes=[],
        )

    coverage = pipeline.status()["coverage"]
    assert coverage["state"] == "CURRENT_WITH_GAPS"
    assert coverage["broker_server"] == "MetaQuotes-Demo"
    assert coverage["latest_completed_m5_open_utc"] == bars[-1].open_time_utc.isoformat()
    assert coverage["latest_decision_m5_open_utc"] == bars[-1].open_time_utc.isoformat()
    assert coverage["unprocessed_archived_bars"] == 2
    assert coverage["first_unprocessed_m5_open_utc"] == bars[1].open_time_utc.isoformat()
    assert coverage["publication_state"] == "BLOCKED"  # the worker has not started


def test_recovered_old_job_is_invalidated_instead_of_evaluated_with_current_candles(tmp_path):
    database = tmp_path / "stale-job.db"
    adapter = PipelineAdapter()
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")
    pipeline.run_once()
    old_anchor = adapter.candles_by_timeframe["M5"][-4].open_time_utc
    enqueue_research_job(database, job_id="old-recovered-job", job_type=pipeline_module.RESEARCH_JOB_TYPE,
                         symbol="XAUUSD", anchor_time_utc=old_anchor,
                         created_at_utc=datetime.now(UTC), payload={"source": "MT5"})

    pipeline.run_once()

    summary = read_pipeline_summary(database, symbol="XAUUSD")
    assert summary["jobs"] == {"COMPLETED": 1, "INVALIDATED": 1}
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM research_runs").fetchone()[0] == 1
        assert "ASOF_CANDLE_MISMATCH" in connection.execute(
            "SELECT reason_codes_json FROM research_jobs WHERE job_id = 'old-recovered-job'"
        ).fetchone()[0]


def test_bar_rollover_during_research_does_not_freeze_newer_snapshot_under_old_anchor(tmp_path):
    class RollingAdapter(PipelineAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.m5_requests = 0

        def candles(self, symbol, timeframe, limit):
            status, reasons, values = super().candles(symbol, timeframe, limit)
            if timeframe != "M5":
                return status, reasons, values
            self.m5_requests += 1
            if self.m5_requests < 3:
                return status, reasons, values
            former_forming = values[-1].model_copy(update={"completed": True})
            new_forming = values[-1].model_copy(update={
                "open_time_utc": values[-1].open_time_utc + timedelta(minutes=5),
                "completed": False,
            })
            return status, reasons, [*values[:-1], former_forming, new_forming]

    database = tmp_path / "rollover.db"
    adapter = RollingAdapter()
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")

    pipeline.run_once()

    summary = read_pipeline_summary(database, symbol="XAUUSD")
    assert summary["jobs"] == {"INVALIDATED": 1}
    assert summary["latest_run"] is None


def test_pipeline_status_does_not_call_old_candles_current_just_because_quote_is_live(tmp_path):
    database = tmp_path / "bar-lag.db"
    adapter = PipelineAdapter()
    adapter.candles_by_timeframe = {
        tf: [bar.model_copy(update={"open_time_utc": bar.open_time_utc - timedelta(days=20)}) for bar in bars]
        for tf, bars in adapter.candles_by_timeframe.items()
    }
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")

    pipeline.run_once()

    status = pipeline.status()
    assert status["last_market_data_status"] == "LIVE"
    assert status["coverage"]["state"] == "BAR_LAGGING"
    assert status["coverage"]["publication_state"] == "BLOCKED"


def test_pipeline_status_blocks_publication_when_worker_reports_an_error(tmp_path):
    database = tmp_path / "worker-error.db"
    adapter = PipelineAdapter()
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")
    pipeline.run_once()

    class ActiveTask:
        def done(self):
            return False

    pipeline._task = ActiveTask()
    pipeline._last_quote_source_timestamp_utc = None
    pipeline._last_error = "OperationalError"

    coverage = pipeline.status()["coverage"]
    assert coverage["state"] == "CURRENT"
    assert coverage["worker_health"] == "ERROR"
    assert coverage["publication_state"] == "BLOCKED"

    pipeline._last_error = None
    pipeline._last_cycle_at_utc = datetime.now(UTC) - timedelta(hours=1)
    coverage = pipeline.status()["coverage"]
    assert coverage["worker_health"] == "STALE"
    assert coverage["publication_state"] == "BLOCKED"


def test_pipeline_publishes_one_frozen_eligible_signal_per_completed_m5_bar(tmp_path):
    class EligibleAdapter(PipelineAdapter):
        def __init__(self, *, spread_history: bool) -> None:
            super().__init__()
            now = datetime.now(UTC).replace(second=0, microsecond=0)
            for timeframe, minutes in TIMEFRAME_MINUTES.items():
                original = self.candles_by_timeframe[timeframe]
                start = now - timedelta(minutes=minutes * (len(original) - 1))
                self.candles_by_timeframe[timeframe] = [
                    candle.model_copy(update={
                        "open_time_utc": start + timedelta(minutes=minutes * index),
                        "spread_points": 20 if spread_history and timeframe == "M5" else None,
                    })
                    for index, candle in enumerate(original)
                ]

        def quote(self, symbol):
            close = self.candles_by_timeframe["M5"][-2].close
            return super().quote(symbol).model_copy(update={
                "bid": close, "ask": close + 0.2, "tick_age_seconds": 0.2,
                "spread_points": 20, "tick_size": 0.01, "tick_value": 1.0,
                "contract_size": 100, "volume_min": 0.01, "volume_max": 100,
                "volume_step": 0.01,
            })

    eligible_db = tmp_path / "eligible.db"
    eligible = EligibleAdapter(spread_history=True)
    coordinator = ResearchCoordinator(eligible, PipelineCalendar(), eligible_db)
    assert coordinator.live_research_watch("XAUUSD").signal_proof.publication_state == "ELIGIBLE"
    pipeline = ResearchPipeline(eligible, PipelineCalendar(), coordinator, eligible_db, lambda: "XAUUSD")
    pipeline.run_once()
    pipeline.run_once()
    entries = read_recent_signal_history(eligible_db, symbol="XAUUSD", limit=10)
    assert len(entries) == 1
    assert entries[0]["signal_kind"] == "AUTOMATIC"
    assert entries[0]["decision"] == "WATCH_LONG"
    assert entries[0]["reference_levels"]["entry"] > entries[0]["reference_levels"]["stop_loss"]
    assert entries[0]["signal_proof"]["publication_state"] == "ELIGIBLE"

    missing_spread_db = tmp_path / "missing-spread.db"
    missing_spread = EligibleAdapter(spread_history=False)
    ResearchPipeline(missing_spread, PipelineCalendar(), ResearchCoordinator(missing_spread, PipelineCalendar(), missing_spread_db), missing_spread_db, lambda: "XAUUSD").run_once()
    assert read_recent_signal_history(missing_spread_db, symbol="XAUUSD", limit=10) == []

    no_breakout_db = tmp_path / "no-breakout.db"
    no_breakout = EligibleAdapter(spread_history=True)
    m5 = no_breakout.candles_by_timeframe["M5"]
    m5[-2] = m5[-2].model_copy(update={"close": m5[-3].close - 0.2})
    no_breakout_coordinator = ResearchCoordinator(no_breakout, PipelineCalendar(), no_breakout_db)
    ResearchPipeline(no_breakout, PipelineCalendar(), no_breakout_coordinator, no_breakout_db, lambda: "XAUUSD").run_once()
    assert read_recent_signal_history(no_breakout_db, symbol="XAUUSD", limit=10) == []


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
        base = original[-2].close + 1 + index
        extension.append(original[-1].model_copy(update={
            "open_time_utc": extension_start + timedelta(minutes=(index + 1) * 5),
            "open": base,
            "high": base + 1,
            "low": base - 1,
            "close": base + 0.5,
            "completed": index < 12,
        }))
    adapter.candles_by_timeframe["M5"] = original[:-1] + [original[-1].model_copy(update={"completed": True})] + extension
    pipeline.run_once()

    with sqlite3.connect(database) as connection:
        labels = connection.execute("SELECT direction, horizon_bars FROM research_labels").fetchall()
    assert labels == [("UP", 12)]


def test_published_signal_followup_waits_for_twelve_contiguous_completed_broker_bars(tmp_path):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    pipeline = ResearchPipeline(adapter, PipelineCalendar(), ResearchCoordinator(adapter, PipelineCalendar(), database), database, lambda: "XAUUSD")
    start = datetime(2026, 10, 20, tzinfo=UTC)
    anchor_close_utc = start + timedelta(minutes=5)
    record_signal_history(
        database, signal_id="auto-followup", provided_at_utc=anchor_close_utc,
        symbol="XAUUSD", source="PYONTRADING2_LIVE_RESEARCH_WATCH",
        source_timestamp_utc=anchor_close_utc, data_status="LIVE",
        analysis_mode="AUTOMATIC_RESEARCH_WATCH_V1", decision="WATCH_SHORT",
        market_context="DOWNWARD_STRUCTURE", summary="Completed-candle short watch",
        event_risk_state="CLEAR", paper_status="NOT_CREATED", input_fingerprint="frozen",
        reason_codes=[], payload={"broker_server": "MetaQuotes-Demo", "watch": {"reference_levels": {
            "source_candle_close_utc": anchor_close_utc.isoformat()}}},
    )
    bars = [Candle(
        open_time_utc=start + timedelta(minutes=5 * index),
        open=4100.0 - index, high=4101.0 - index, low=4099.0 - index,
        close=4100.0 - index, tick_volume=10, completed=True,
    ) for index in range(13)]
    def archive(values, broker_server="MetaQuotes-Demo"):
        store_completed_candles(database, source="MT5", broker_server=broker_server,
                                symbol="XAUUSD", timeframe="M5", candles=values,
                                timeframe_seconds=300, observed_at_utc=datetime.now(UTC))

    archive(bars[:12])
    pipeline._label_mature_runs("XAUUSD", "MetaQuotes-Demo", datetime.now(UTC))
    assert read_recent_signal_history(database, symbol="XAUUSD", limit=10)[0]["forward_outcome"] is None

    archive(bars[12:])
    pipeline._label_mature_runs("XAUUSD", "Other-Broker", datetime.now(UTC))
    assert read_recent_signal_history(database, symbol="XAUUSD", limit=10)[0]["forward_outcome"] is None

    pipeline._label_mature_runs("XAUUSD", "MetaQuotes-Demo", datetime.now(UTC))
    outcome = read_recent_signal_history(database, symbol="XAUUSD", limit=10)[0]["forward_outcome"]
    assert outcome["directional_state"] == "FAVORABLE"
    assert outcome["directional_change"] == 12.0
    assert outcome["outcome_close_utc"] == (start + timedelta(minutes=65)).isoformat()

    record_signal_history(
        database, signal_id="auto-gap", provided_at_utc=anchor_close_utc,
        symbol="XAUUSD", source="PYONTRADING2_LIVE_RESEARCH_WATCH",
        source_timestamp_utc=anchor_close_utc, data_status="LIVE",
        analysis_mode="AUTOMATIC_RESEARCH_WATCH_V1", decision="WATCH_SHORT",
        market_context="DOWNWARD_STRUCTURE", summary="Broker gap test",
        event_risk_state="CLEAR", paper_status="NOT_CREATED", input_fingerprint="gap-frozen",
        reason_codes=[], payload={"broker_server": "Gap-Broker", "watch": {"reference_levels": {
            "source_candle_close_utc": anchor_close_utc.isoformat()}}},
    )
    archive(bars[:6] + bars[7:], broker_server="Gap-Broker")
    pipeline._label_mature_runs("XAUUSD", "Gap-Broker", datetime.now(UTC))
    gap = next(entry for entry in read_recent_signal_history(database, symbol="XAUUSD", limit=10)
               if entry["signal_id"] == "auto-gap")
    assert gap["forward_outcome"] is None


def test_background_cycle_keeps_the_async_event_loop_responsive(tmp_path):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    calendar = PipelineCalendar()
    coordinator = ResearchCoordinator(adapter, calendar, database)
    pipeline = ResearchPipeline(adapter, calendar, coordinator, database, lambda: "XAUUSD")

    def slow_cycle() -> None:
        time.sleep(0.06)

    pipeline.run_once = slow_cycle  # type: ignore[method-assign]

    async def scenario() -> int:
        ticks = 0
        running = True

        async def heartbeat() -> None:
            nonlocal ticks
            while running:
                ticks += 1
                await asyncio.sleep(0.005)

        task = asyncio.create_task(heartbeat())
        try:
            assert await pipeline._run_cycle() is True
        finally:
            running = False
            await task
            await pipeline.stop()
        return ticks

    assert asyncio.run(scenario()) >= 5


def test_paused_research_pipeline_does_not_collect_and_resumes_from_persisted_control(tmp_path):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")

    write_operation_control(database, key="research_pipeline_enabled", value="false", actor="TEST_OPERATOR", action="RESEARCH_PIPELINE_PAUSED")
    pipeline.run_once()
    assert adapter.candle_requests == []
    assert pipeline.status()["enabled"] is False

    async def paused_status() -> dict[str, object]:
        await pipeline.start()
        try:
            await asyncio.sleep(0)
            return pipeline.status()
        finally:
            await pipeline.stop()

    paused = asyncio.run(paused_status())
    assert paused["state"] == "PAUSED"
    assert all(worker["state"] == "PAUSED" for worker in paused["workers"])

    write_operation_control(database, key="research_pipeline_enabled", value="true", actor="TEST_OPERATOR", action="RESEARCH_PIPELINE_RESUMED")
    pipeline.run_once()
    assert adapter.candle_requests
    assert pipeline.status()["enabled"] is True


def test_research_worker_survives_a_temporary_control_store_failure(tmp_path, monkeypatch):
    database = tmp_path / "research.db"
    adapter = PipelineAdapter()
    calendar = PipelineCalendar()
    pipeline = ResearchPipeline(adapter, calendar, ResearchCoordinator(adapter, calendar, database), database, lambda: "XAUUSD")
    attempts = 0

    def unavailable_control(_database_path) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        raise sqlite3.OperationalError("control store unavailable")

    monkeypatch.setattr(pipeline_module, "read_operations_status", unavailable_control)

    async def scenario() -> None:
        await pipeline.start()
        try:
            await asyncio.sleep(0.02)
            assert pipeline._task is not None and not pipeline._task.done()
            assert pipeline._last_error == "OperationalError"
            assert adapter.candle_requests == []
        finally:
            await pipeline.stop()

    asyncio.run(scenario())
    assert attempts >= 1

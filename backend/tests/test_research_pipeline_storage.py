from datetime import UTC, datetime, timedelta

from app.schemas.market import Candle
from app.storage.database import (
    claim_next_research_job,
    complete_research_job,
    count_completed_candles,
    enqueue_research_job,
    read_completed_candles,
    read_recent_signal_history,
    record_model_version,
    record_outcome_label,
    record_signal_history,
    record_strategy_journal_events,
    read_recent_strategy_journal_events,
    record_research_run,
    store_completed_candles,
    initialize_database,
)


def candle(index: int, *, completed: bool = True) -> Candle:
    return Candle(
        open_time_utc=datetime(2026, 10, 20, tzinfo=UTC) + timedelta(minutes=index * 5),
        open=4100 + index,
        high=4101 + index,
        low=4099 + index,
        close=4100.5 + index,
        tick_volume=10 + index,
        real_volume=index,
        spread_points=30,
        completed=completed,
    )


def test_completed_candles_are_immutable_and_exclude_forming_bar(tmp_path):
    database = tmp_path / "research.db"
    observed_at = datetime(2026, 10, 21, tzinfo=UTC)
    candles = [candle(0), candle(1), candle(2, completed=False)]

    inserted = store_completed_candles(
        database,
        source="MT5",
        broker_server=None,
        symbol="XAUUSD",
        timeframe="M5",
        candles=candles,
        timeframe_seconds=300,
        observed_at_utc=observed_at,
    )

    assert inserted == 2
    assert count_completed_candles(database, symbol="XAUUSD", timeframe="M5") == 2
    assert store_completed_candles(
        database,
        source="MT5",
        broker_server=None,
        symbol="XAUUSD",
        timeframe="M5",
        candles=candles,
        timeframe_seconds=300,
        observed_at_utc=observed_at + timedelta(minutes=1),
    ) == 0

    persisted = read_completed_candles(database, symbol="XAUUSD", timeframe="M5", limit=10)
    assert [item.open_time_utc for item in persisted] == [candles[0].open_time_utc, candles[1].open_time_utc]
    assert persisted[0].close == candles[0].close
    assert all(item.completed for item in persisted)


def test_research_job_claim_completion_and_immutable_records(tmp_path):
    database = tmp_path / "research.db"
    anchor = datetime(2026, 10, 21, tzinfo=UTC)
    enqueue_research_job(
        database,
        job_id="job-1",
        job_type="RESEARCH_SNAPSHOT",
        symbol="XAUUSD",
        anchor_time_utc=anchor,
        created_at_utc=anchor,
        payload={"timeframes": ["M5", "M15", "H1", "H4"]},
    )
    enqueue_research_job(
        database,
        job_id="job-duplicate",
        job_type="RESEARCH_SNAPSHOT",
        symbol="XAUUSD",
        anchor_time_utc=anchor,
        created_at_utc=anchor,
        payload={},
    )

    job = claim_next_research_job(database)
    assert job is not None
    assert job["job_id"] == "job-1"
    assert job["anchor_time_utc"] == anchor
    assert claim_next_research_job(database) is None

    record_research_run(
        database,
        run_id="run-1",
        job_id=job["job_id"],
        observed_at_utc=anchor,
        symbol="XAUUSD",
        anchor_time_utc=anchor,
        trigger="COMPLETED_M5_BAR",
        data_status="LIVE",
        feature_set_version="mtf-research-v1",
        source_statuses={"M5": "LIVE"},
        response={"market_state": "NO TRADE"},
        reason_codes=["NOT_A_TRADE_SIGNAL"],
    )
    record_outcome_label(
        database,
        run_id="run-1",
        label_version="m5-close-direction-v1",
        horizon_bars=12,
        anchor_close=4100.0,
        outcome_close=4102.5,
        labelled_at_utc=anchor + timedelta(hours=1),
    )
    record_model_version(
        database,
        model_version_id="model-1",
        created_at_utc=anchor,
        model_kind="DETERMINISTIC_STRATEGY_CALIBRATION",
        model_version="training-v1",
        state="REVIEW_REQUIRED",
        symbol="XAUUSD",
        timeframe="M5",
        dataset_start_utc=anchor,
        dataset_end_utc=anchor,
        dataset_candles=0,
        feature_set_version="mtf-research-v1",
        metrics={},
        payload={},
        reason_codes=["NO_MODEL_PROMOTION"],
    )
    complete_research_job(database, job_id=job["job_id"], reason_codes=["NOT_A_TRADE_SIGNAL"])

    assert claim_next_research_job(database) is None


def test_future_timestamp_archive_is_quarantined_on_guard_migration(tmp_path):
    import sqlite3

    database = tmp_path / "research.db"
    initialize_database(database)
    future_open = datetime.now(UTC) + timedelta(hours=3)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO market_candles("
            "source, broker_server, symbol, timeframe, open_time_utc, close_time_utc, open, high, low, close, "
            "tick_volume, real_volume, spread_points, observed_at_utc"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "MT5", "MetaQuotes-Demo", "XAUUSD", "M5", future_open.isoformat(),
                (future_open + timedelta(minutes=5)).isoformat(), 4100.0, 4101.0, 4099.0, 4100.5,
                10, 0, 30, datetime.now(UTC).isoformat(),
            ),
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = 2")
        connection.commit()

    initialize_database(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM market_candles").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM quarantined_market_candles").fetchone()[0] == 1
        assert connection.execute("SELECT reason_code FROM source_data_quarantines").fetchone()[0] == "FUTURE_BROKER_TIMESTAMP"


def test_strategy_module_journal_is_append_only_by_decision_time_and_version(tmp_path):
    database = tmp_path / "research.db"
    observed = datetime(2026, 10, 23, tzinfo=UTC)
    event = {
        "strategy_id": "VWAP_VOLUME_MOMENTUM",
        "strategy_version": "vwap-tick-proxy-momentum-v1",
        "state": "OBSERVING",
        "direction": "ABSTAIN",
        "data_sources": ["BROKER_TICK_PROXY"],
        "reason_codes": ["COMPLETED_CANDLES_ONLY"],
    }

    assert record_strategy_journal_events(
        database, observed_at_utc=observed, symbol="XAUUSD", candle_open_utc=observed,
        disposition="REVIEW_REQUIRED", modules=[event],
    ) == 1
    assert record_strategy_journal_events(
        database, observed_at_utc=observed + timedelta(minutes=5), symbol="XAUUSD", candle_open_utc=observed,
        disposition="REJECTED", modules=[event],
    ) == 0

    records = read_recent_strategy_journal_events(database, symbol="XAUUSD")
    assert len(records) == 1
    assert records[0]["disposition"] == "REVIEW_REQUIRED"
    assert records[0]["data_sources"] == ["BROKER_TICK_PROXY"]


def test_signal_history_retains_the_exact_user_visible_research_result(tmp_path):
    database = tmp_path / "research.db"
    observed = datetime(2026, 10, 23, tzinfo=UTC)
    record_signal_history(
        database, signal_id="signal-1", provided_at_utc=observed, symbol="XAUUSD",
        source="PYONTRADING2_RESEARCH_SCREEN", source_timestamp_utc=observed,
        data_status="LIVE", analysis_mode="RESEARCH_SCREEN_V4_PROFESSIONAL_MODULES",
        decision="NO_TRADE", market_context="MIXED_STRUCTURE", summary="Evidence is incomplete.",
        event_risk_state="CLEAR", paper_status="NOT_CREATED", input_fingerprint="fingerprint-1",
        reason_codes=["NO_ORDER_EXECUTION"], payload={"decision": "NO_TRADE", "gates": []},
    )

    records = read_recent_signal_history(database, symbol="XAUUSD", limit=10)

    assert len(records) == 1
    assert records[0]["signal_id"] == "signal-1"
    assert records[0]["decision"] == "NO_TRADE"
    assert records[0]["reason_codes"] == ["NO_ORDER_EXECUTION"]
    assert records[0]["input_fingerprint"] == "fingerprint-1"


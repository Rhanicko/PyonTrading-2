from datetime import UTC, datetime
from pathlib import Path

from app.storage.database import (
    read_recent_evaluations,
    read_settings,
    read_strategy_settings,
    record_evaluation,
    write_settings,
    write_strategy_setting,
)


def test_settings_round_trip(tmp_path: Path):
    database = tmp_path / "settings.db"
    write_settings(database, {"symbol": "XAUUSDm", "max_risk_percent": "0.5"})
    assert read_settings(database)["symbol"] == "XAUUSDm"


def test_strategy_enablement_is_scoped_by_exact_broker_symbol(tmp_path: Path):
    database = tmp_path / "settings.db"
    write_strategy_setting(
        database, symbol="XAUUSDm", strategy_id="MOMENTUM_ALIGNMENT", enabled=False,
    )

    configured = read_strategy_settings(database, symbol="XAUUSDm")

    assert configured["MOMENTUM_ALIGNMENT"]["enabled"] is False
    assert configured["MOMENTUM_ALIGNMENT"]["updated_at_utc"].tzinfo is not None
    assert read_strategy_settings(database, symbol="XAUUSD") == {}


def test_journal_keeps_one_immutable_observation_per_completed_candle(tmp_path: Path):
    database = tmp_path / "journal.db"
    now = datetime(2026, 10, 21, 12, 5, tzinfo=UTC)
    values = {
        "evaluation_at_utc": now,
        "symbol": "XAUUSD",
        "candle_open_utc": datetime(2026, 10, 21, 12, 0, tzinfo=UTC),
        "quote_source_timestamp_utc": now,
        "quote_bid": 4100.5,
        "quote_ask": 4100.8,
        "quote_status": "LIVE",
        "reason_codes": ["PHASE_2_STRATEGY_NOT_IMPLEMENTED", "NO_ORDER_EXECUTION"],
    }
    record_evaluation(database, **values)
    record_evaluation(database, **{**values, "quote_bid": 9999.0})

    rows = read_recent_evaluations(database)
    assert len(rows) == 1
    assert rows[0]["quote_bid"] == 4100.5
    assert rows[0]["market_state"] == "NO TRADE"


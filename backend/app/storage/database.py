from __future__ import annotations

import sqlite3
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


RESEARCH_PIPELINE_MIGRATION = 1
SOURCE_CLOCK_GUARD_MIGRATION = 2
TIMESTAMP_NORMALIZATION_MIGRATION = 3
RESEARCH_OPERATIONS_MIGRATION = 4
BROKER_SESSION_TRANSITIONS_MIGRATION = 5
STRATEGY_JOURNAL_MIGRATION = 6
SIGNAL_HISTORY_MIGRATION = 7
STRATEGY_CONFIGURATION_MIGRATION = 8
MAX_FUTURE_SOURCE_SECONDS = 60


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at_utc TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS local_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at_utc TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS journal_evaluations ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "evaluation_at_utc TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, "
            "candle_open_utc TEXT NOT NULL, quote_source_timestamp_utc TEXT, quote_bid REAL, quote_ask REAL, "
            "quote_status TEXT NOT NULL, market_state TEXT NOT NULL, evaluation_type TEXT NOT NULL, "
            "strategy_version TEXT NOT NULL, reason_codes_json TEXT NOT NULL, "
            "UNIQUE(symbol, timeframe, candle_open_utc, strategy_version)"
            ")"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_journal_evaluations_recent ON journal_evaluations(evaluation_at_utc DESC)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS research_evidence ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at_utc TEXT NOT NULL, symbol TEXT NOT NULL, "
            "candle_open_utc TEXT NOT NULL, window_hours INTEGER NOT NULL, chart_structure TEXT NOT NULL, "
            "calendar_state TEXT NOT NULL, consensus_state TEXT NOT NULL, source_statuses_json TEXT NOT NULL, "
            "UNIQUE(symbol, candle_open_utc, window_hours)"
            ")"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_research_evidence_symbol ON research_evidence(symbol, observed_at_utc DESC)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS calendar_cache ("
            "provider TEXT PRIMARY KEY, fetched_at_utc TEXT NOT NULL, payload_json TEXT NOT NULL"
            ")"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS backtest_runs ("
            "run_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, "
            "dataset_start_utc TEXT, dataset_end_utc TEXT, completed_candles INTEGER NOT NULL, data_status TEXT NOT NULL, "
            "reason_codes_json TEXT NOT NULL, payload_json TEXT NOT NULL"
            ")"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_backtest_runs_recent ON backtest_runs(created_at_utc DESC)")
        _apply_research_pipeline_migrations(connection)
        connection.commit()


def _apply_research_pipeline_migrations(connection: sqlite3.Connection) -> None:
    """Apply additive, forward-only migrations for durable research work."""
    applied = {
        int(row[0])
        for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    if RESEARCH_PIPELINE_MIGRATION not in applied:
        _create_research_pipeline_tables(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (RESEARCH_PIPELINE_MIGRATION,),
        )
    if SOURCE_CLOCK_GUARD_MIGRATION not in applied:
        _apply_source_clock_guard(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (SOURCE_CLOCK_GUARD_MIGRATION,),
        )
    if TIMESTAMP_NORMALIZATION_MIGRATION not in applied:
        _apply_timestamp_normalization_columns(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (TIMESTAMP_NORMALIZATION_MIGRATION,),
        )
    if RESEARCH_OPERATIONS_MIGRATION not in applied:
        _create_research_operations_tables(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (RESEARCH_OPERATIONS_MIGRATION,),
        )
    if BROKER_SESSION_TRANSITIONS_MIGRATION not in applied:
        _create_broker_session_transition_table(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (BROKER_SESSION_TRANSITIONS_MIGRATION,),
        )
    if STRATEGY_JOURNAL_MIGRATION not in applied:
        _create_strategy_journal_table(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (STRATEGY_JOURNAL_MIGRATION,),
        )
    if SIGNAL_HISTORY_MIGRATION not in applied:
        _create_signal_history_table(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (SIGNAL_HISTORY_MIGRATION,),
        )
    if STRATEGY_CONFIGURATION_MIGRATION not in applied:
        _create_strategy_configuration_table(connection)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at_utc) VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (STRATEGY_CONFIGURATION_MIGRATION,),
        )


def _create_research_pipeline_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS market_candles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, broker_server TEXT NOT NULL, symbol TEXT NOT NULL, "
        "timeframe TEXT NOT NULL, open_time_utc TEXT NOT NULL, close_time_utc TEXT NOT NULL, "
        "open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, "
        "tick_volume INTEGER NOT NULL, real_volume INTEGER, spread_points INTEGER, observed_at_utc TEXT NOT NULL, "
        "UNIQUE(source, broker_server, symbol, timeframe, open_time_utc)"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_candles_lookup "
        "ON market_candles(symbol, timeframe, open_time_utc)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS research_jobs ("
        "job_id TEXT PRIMARY KEY, job_type TEXT NOT NULL, symbol TEXT NOT NULL, anchor_time_utc TEXT NOT NULL, "
        "state TEXT NOT NULL, created_at_utc TEXT NOT NULL, started_at_utc TEXT, completed_at_utc TEXT, "
        "attempt_count INTEGER NOT NULL DEFAULT 0, reason_codes_json TEXT NOT NULL, payload_json TEXT NOT NULL, "
        "UNIQUE(job_type, symbol, anchor_time_utc)"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_jobs_next "
        "ON research_jobs(state, created_at_utc)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS research_runs ("
        "run_id TEXT PRIMARY KEY, job_id TEXT UNIQUE REFERENCES research_jobs(job_id), "
        "observed_at_utc TEXT NOT NULL, symbol TEXT NOT NULL, anchor_time_utc TEXT NOT NULL, "
        "trigger TEXT NOT NULL, data_status TEXT NOT NULL, feature_set_version TEXT NOT NULL, "
        "source_statuses_json TEXT NOT NULL, response_json TEXT NOT NULL, reason_codes_json TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_runs_symbol "
        "ON research_runs(symbol, anchor_time_utc DESC)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS research_labels ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES research_runs(run_id), "
        "label_version TEXT NOT NULL, horizon_bars INTEGER NOT NULL, anchor_close REAL NOT NULL, "
        "outcome_close REAL NOT NULL, outcome_price_delta REAL NOT NULL, direction TEXT NOT NULL, "
        "labelled_at_utc TEXT NOT NULL, UNIQUE(run_id, label_version, horizon_bars)"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS calendar_snapshots ("
        "snapshot_id TEXT PRIMARY KEY, observed_at_utc TEXT NOT NULL, source TEXT NOT NULL, "
        "source_url TEXT NOT NULL, source_timestamp_utc TEXT, data_status TEXT NOT NULL, "
        "reason_codes_json TEXT NOT NULL, payload_json TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_calendar_snapshots_recent "
        "ON calendar_snapshots(observed_at_utc DESC)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS model_versions ("
        "model_version_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL, model_kind TEXT NOT NULL, "
        "model_version TEXT NOT NULL, state TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, "
        "dataset_start_utc TEXT, dataset_end_utc TEXT, dataset_candles INTEGER NOT NULL, "
        "feature_set_version TEXT NOT NULL, metrics_json TEXT NOT NULL, payload_json TEXT NOT NULL, "
        "reason_codes_json TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_model_versions_symbol "
        "ON model_versions(symbol, created_at_utc DESC)"
    )


def _apply_source_clock_guard(connection: sqlite3.Connection) -> None:
    """Quarantine an entire archive when its current broker time violates MT5's UTC contract."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS quarantined_market_candles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, original_market_candle_id INTEGER NOT NULL, source TEXT NOT NULL, "
        "broker_server TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, open_time_utc TEXT NOT NULL, "
        "close_time_utc TEXT NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, "
        "tick_volume INTEGER NOT NULL, real_volume INTEGER, spread_points INTEGER, observed_at_utc TEXT NOT NULL, "
        "quarantined_at_utc TEXT NOT NULL, reason_code TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS source_data_quarantines ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, broker_server TEXT NOT NULL, symbol TEXT NOT NULL, "
        "reason_code TEXT NOT NULL, quarantined_at_utc TEXT NOT NULL, raw_candle_count INTEGER NOT NULL, "
        "latest_open_time_utc TEXT NOT NULL, UNIQUE(source, broker_server, symbol, reason_code)"
        ")"
    )
    research_run_columns = {row[1] for row in connection.execute("PRAGMA table_info(research_runs)")}
    if "invalidated_at_utc" not in research_run_columns:
        connection.execute("ALTER TABLE research_runs ADD COLUMN invalidated_at_utc TEXT")
    model_version_columns = {row[1] for row in connection.execute("PRAGMA table_info(model_versions)")}
    if "invalidated_at_utc" not in model_version_columns:
        connection.execute("ALTER TABLE model_versions ADD COLUMN invalidated_at_utc TEXT")
    cutoff = datetime.now(UTC) + timedelta(seconds=MAX_FUTURE_SOURCE_SECONDS)
    quarantined_at = datetime.now(UTC).isoformat()
    offenders = connection.execute(
        "SELECT source, broker_server, symbol, COUNT(*) AS candle_count, MAX(open_time_utc) AS latest_open_time_utc "
        "FROM market_candles GROUP BY source, broker_server, symbol "
        "HAVING julianday(MAX(open_time_utc)) > julianday(?)",
        (cutoff.isoformat(),),
    ).fetchall()
    for source, broker_server, symbol, candle_count, latest_open_time_utc in offenders:
        connection.execute(
            "INSERT INTO quarantined_market_candles("
            "original_market_candle_id, source, broker_server, symbol, timeframe, open_time_utc, close_time_utc, "
            "open, high, low, close, tick_volume, real_volume, spread_points, observed_at_utc, quarantined_at_utc, reason_code"
            ") SELECT id, source, broker_server, symbol, timeframe, open_time_utc, close_time_utc, open, high, low, close, "
            "tick_volume, real_volume, spread_points, observed_at_utc, ?, 'FUTURE_BROKER_TIMESTAMP' "
            "FROM market_candles WHERE source = ? AND broker_server = ? AND symbol = ?",
            (quarantined_at, source, broker_server, symbol),
        )
        connection.execute(
            "INSERT INTO source_data_quarantines("
            "source, broker_server, symbol, reason_code, quarantined_at_utc, raw_candle_count, latest_open_time_utc"
            ") VALUES (?, ?, ?, 'FUTURE_BROKER_TIMESTAMP', ?, ?, ?) "
            "ON CONFLICT(source, broker_server, symbol, reason_code) DO UPDATE SET "
            "quarantined_at_utc=excluded.quarantined_at_utc, raw_candle_count=excluded.raw_candle_count, "
            "latest_open_time_utc=excluded.latest_open_time_utc",
            (source, broker_server, symbol, quarantined_at, candle_count, latest_open_time_utc),
        )
        connection.execute(
            "DELETE FROM market_candles WHERE source = ? AND broker_server = ? AND symbol = ?",
            (source, broker_server, symbol),
        )
        connection.execute(
            "UPDATE research_jobs SET state = 'INVALIDATED', completed_at_utc = ?, "
            "reason_codes_json = '[\"FUTURE_BROKER_TIMESTAMP\"]' "
            "WHERE symbol = ? AND julianday(anchor_time_utc) > julianday(?)",
            (quarantined_at, symbol, cutoff.isoformat()),
        )
        connection.execute(
            "UPDATE research_runs SET invalidated_at_utc = ? WHERE symbol = ? AND invalidated_at_utc IS NULL "
            "AND julianday(anchor_time_utc) > julianday(?)",
            (quarantined_at, symbol, cutoff.isoformat()),
        )
        connection.execute(
            "UPDATE model_versions SET invalidated_at_utc = ? WHERE symbol = ? AND invalidated_at_utc IS NULL "
            "AND dataset_end_utc IS NOT NULL AND julianday(dataset_end_utc) > julianday(?)",
            (quarantined_at, symbol, cutoff.isoformat()),
        )


def _apply_timestamp_normalization_columns(connection: sqlite3.Connection) -> None:
    """Retain raw MT5 time alongside the explicitly normalized effective time."""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(market_candles)")}
    if "raw_open_time_utc" not in columns:
        connection.execute("ALTER TABLE market_candles ADD COLUMN raw_open_time_utc TEXT")
    if "broker_clock_offset_seconds" not in columns:
        connection.execute(
            "ALTER TABLE market_candles ADD COLUMN broker_clock_offset_seconds INTEGER NOT NULL DEFAULT 0"
        )
    if "timestamp_normalized" not in columns:
        connection.execute(
            "ALTER TABLE market_candles ADD COLUMN timestamp_normalized INTEGER NOT NULL DEFAULT 0"
        )


def _create_research_operations_tables(connection: sqlite3.Connection) -> None:
    """Persist frozen research decisions and local-only paper/operations evidence."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS frozen_research_decisions ("
        "decision_id TEXT PRIMARY KEY, observed_at_utc TEXT NOT NULL, symbol TEXT NOT NULL, "
        "anchor_time_utc TEXT NOT NULL, decision TEXT NOT NULL, feature_set_version TEXT NOT NULL, "
        "input_fingerprint TEXT NOT NULL, quote_source_timestamp_utc TEXT, quote_bid REAL, quote_ask REAL, "
        "spread_points REAL, data_quality_state TEXT NOT NULL, event_risk_state TEXT NOT NULL, "
        "session_regime TEXT NOT NULL, model_promotion_state TEXT NOT NULL, paper_status TEXT NOT NULL, "
        "feature_snapshot_json TEXT NOT NULL, ensemble_json TEXT NOT NULL, costs_json TEXT NOT NULL, "
        "reason_codes_json TEXT NOT NULL, UNIQUE(symbol, anchor_time_utc, feature_set_version)"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_frozen_research_decisions_symbol "
        "ON frozen_research_decisions(symbol, anchor_time_utc DESC)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS paper_decision_labels ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, decision_id TEXT NOT NULL REFERENCES frozen_research_decisions(decision_id), "
        "label_version TEXT NOT NULL, horizon_bars INTEGER NOT NULL, anchor_close REAL NOT NULL, "
        "outcome_close REAL NOT NULL, outcome_price_delta REAL NOT NULL, directional_match INTEGER, "
        "labelled_at_utc TEXT NOT NULL, UNIQUE(decision_id, label_version, horizon_bars)"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS research_operations_controls ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at_utc TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS research_operations_audit ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at_utc TEXT NOT NULL, actor TEXT NOT NULL, "
        "action TEXT NOT NULL, payload_json TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS broker_session_transitions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, previous_state TEXT NOT NULL, "
        "current_state TEXT NOT NULL, observed_at_utc TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_session_transitions_symbol "
        "ON broker_session_transitions(symbol, observed_at_utc DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_operations_audit_recent "
        "ON research_operations_audit(occurred_at_utc DESC)"
    )
    connection.execute(
        "INSERT OR IGNORE INTO research_operations_controls(key, value, updated_at_utc) "
        "VALUES ('paper_kill_switch', 'false', strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
    )
    connection.execute(
        "INSERT OR IGNORE INTO research_operations_controls(key, value, updated_at_utc) "
        "VALUES ('model_promotion_state', 'REVIEW_REQUIRED', strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
    )


def _create_broker_session_transition_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS broker_session_transitions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, previous_state TEXT NOT NULL, "
        "current_state TEXT NOT NULL, observed_at_utc TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_broker_session_transitions_symbol "
        "ON broker_session_transitions(symbol, observed_at_utc DESC)"
    )


def _create_strategy_journal_table(connection: sqlite3.Connection) -> None:
    """Append-only strategy observations, distinct from hypothetical outcomes."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS strategy_journal_events ("
        "event_id TEXT PRIMARY KEY, occurred_at_utc TEXT NOT NULL, symbol TEXT NOT NULL, candle_open_utc TEXT NOT NULL, "
        "strategy_id TEXT NOT NULL, strategy_version TEXT NOT NULL, state TEXT NOT NULL, direction TEXT NOT NULL, "
        "disposition TEXT NOT NULL, data_sources_json TEXT NOT NULL, reason_codes_json TEXT NOT NULL, evidence_json TEXT NOT NULL, "
        "UNIQUE(symbol, candle_open_utc, strategy_id, strategy_version, state)"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_strategy_journal_events_recent "
        "ON strategy_journal_events(symbol, occurred_at_utc DESC)"
    )


def _create_signal_history_table(connection: sqlite3.Connection) -> None:
    """Append-only record of research screens delivered after a user request."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS signal_history ("
        "signal_id TEXT PRIMARY KEY, provided_at_utc TEXT NOT NULL, symbol TEXT, source TEXT NOT NULL, "
        "source_timestamp_utc TEXT, data_status TEXT NOT NULL, analysis_mode TEXT NOT NULL, decision TEXT NOT NULL, "
        "market_context TEXT NOT NULL, summary TEXT NOT NULL, event_risk_state TEXT NOT NULL, paper_status TEXT, "
        "input_fingerprint TEXT NOT NULL, reason_codes_json TEXT NOT NULL, payload_json TEXT NOT NULL"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_signal_history_symbol_recent "
        "ON signal_history(symbol, provided_at_utc DESC)"
    )


def _create_strategy_configuration_table(connection: sqlite3.Connection) -> None:
    """Persist owner-controlled strategy enablement without rewriting evidence.

    A strategy configuration is intentionally separate from the immutable
    journal: a later toggle must never alter what an earlier completed-candle
    observation recorded.
    """
    connection.execute(
        "CREATE TABLE IF NOT EXISTS research_strategy_settings ("
        "symbol TEXT NOT NULL, strategy_id TEXT NOT NULL, enabled INTEGER NOT NULL "
        "CHECK(enabled IN (0, 1)), updated_at_utc TEXT NOT NULL, "
        "PRIMARY KEY(symbol, strategy_id)"
        ")"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_strategy_settings_symbol "
        "ON research_strategy_settings(symbol, strategy_id)"
    )


def read_settings(path: Path) -> dict[str, str]:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        return dict(connection.execute("SELECT key, value FROM local_settings").fetchall())


def read_strategy_settings(path: Path, *, symbol: str | None) -> dict[str, dict[str, Any]]:
    """Return explicit local strategy choices for one broker symbol only."""
    if not symbol:
        return {}
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT strategy_id, enabled, updated_at_utc FROM research_strategy_settings "
            "WHERE symbol = ? ORDER BY strategy_id ASC",
            (symbol,),
        ).fetchall()
    return {
        str(strategy_id): {
            "enabled": bool(enabled),
            "updated_at_utc": datetime.fromisoformat(str(updated_at_utc)),
        }
        for strategy_id, enabled, updated_at_utc in rows
    }


def write_strategy_setting(path: Path, *, symbol: str, strategy_id: str, enabled: bool) -> None:
    """Upsert one local owner decision using a forward-only settings record."""
    initialize_database(path)
    now = datetime.now(UTC)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO research_strategy_settings(symbol, strategy_id, enabled, updated_at_utc) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(symbol, strategy_id) DO UPDATE SET "
            "enabled = excluded.enabled, updated_at_utc = excluded.updated_at_utc",
            (symbol, strategy_id, int(enabled), now.isoformat()),
        )
        connection.commit()


def record_signal_history(
    path: Path,
    *,
    signal_id: str,
    provided_at_utc: datetime,
    symbol: str | None,
    source: str,
    source_timestamp_utc: datetime | None,
    data_status: str,
    analysis_mode: str,
    decision: str,
    market_context: str,
    summary: str,
    event_risk_state: str,
    paper_status: str | None,
    input_fingerprint: str,
    reason_codes: list[str],
    payload: dict[str, Any],
) -> None:
    """Persist a user-visible research result without changing its evidence payload."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO signal_history("
            "signal_id, provided_at_utc, symbol, source, source_timestamp_utc, data_status, analysis_mode, "
            "decision, market_context, summary, event_risk_state, paper_status, input_fingerprint, "
            "reason_codes_json, payload_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                signal_id, provided_at_utc.isoformat(), symbol, source,
                source_timestamp_utc.isoformat() if source_timestamp_utc else None,
                data_status, analysis_mode, decision, market_context, summary, event_risk_state, paper_status,
                input_fingerprint, json.dumps(reason_codes, sort_keys=True), json.dumps(payload, sort_keys=True),
            ),
        )
        connection.commit()


def read_recent_signal_history(path: Path, *, symbol: str | None, limit: int) -> list[dict[str, Any]]:
    """Return a compact audit view; the exact immutable evidence stays in payload_json."""
    initialize_database(path)
    clause = " WHERE symbol = ?" if symbol is not None else ""
    parameters: tuple[Any, ...] = (symbol, limit) if symbol is not None else (limit,)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        records = connection.execute(
            "SELECT signal_id, provided_at_utc, symbol, source, source_timestamp_utc, data_status, analysis_mode, "
            "decision, market_context, summary, event_risk_state, paper_status, input_fingerprint, reason_codes_json "
            "FROM signal_history" + clause + " ORDER BY provided_at_utc DESC LIMIT ?",
            parameters,
        ).fetchall()
    return [
        {
            **{key: value for key, value in dict(record).items() if key != "reason_codes_json"},
            "reason_codes": json.loads(record["reason_codes_json"]),
        }
        for record in records
    ]


def write_settings(path: Path, values: dict[str, str]) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        for key, value in values.items():
            connection.execute(
                "INSERT INTO local_settings(key, value, updated_at_utc) VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at_utc=excluded.updated_at_utc",
                (key, value),
            )
        connection.commit()


def record_evaluation(
    path: Path,
    *,
    evaluation_at_utc: datetime,
    symbol: str,
    candle_open_utc: datetime,
    quote_source_timestamp_utc: datetime | None,
    quote_bid: float | None,
    quote_ask: float | None,
    quote_status: str,
    reason_codes: list[str],
) -> None:
    """Append one data-only M5 observation; the unique key makes existing rows immutable."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO journal_evaluations("
            "evaluation_at_utc, symbol, timeframe, candle_open_utc, quote_source_timestamp_utc, quote_bid, quote_ask, "
            "quote_status, market_state, evaluation_type, strategy_version, reason_codes_json"
            ") VALUES (?, ?, 'M5', ?, ?, ?, ?, ?, 'NO TRADE', 'DATA_OBSERVATION', 'phase1-data-only-v1', ?) "
            "ON CONFLICT(symbol, timeframe, candle_open_utc, strategy_version) DO NOTHING",
            (
                evaluation_at_utc.isoformat(), symbol, candle_open_utc.isoformat(),
                quote_source_timestamp_utc.isoformat() if quote_source_timestamp_utc else None,
                quote_bid, quote_ask, quote_status, json.dumps(reason_codes),
            ),
        )
        connection.commit()


def read_recent_evaluations(path: Path, limit: int = 3) -> list[dict[str, Any]]:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        records = connection.execute(
            "SELECT id, evaluation_at_utc, symbol, timeframe, candle_open_utc, quote_source_timestamp_utc, "
            "quote_bid, quote_ask, quote_status, market_state, evaluation_type, strategy_version, reason_codes_json "
            "FROM journal_evaluations ORDER BY evaluation_at_utc DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            **{key: value for key, value in dict(record).items() if key != "reason_codes_json"},
            "reason_codes": json.loads(record["reason_codes_json"]),
        }
        for record in records
    ]


def record_research_evidence(
    path: Path,
    *,
    observed_at_utc: datetime,
    symbol: str,
    candle_open_utc: datetime,
    chart_structure: str,
    calendar_state: str,
    consensus_state: str,
    source_statuses: dict[str, str],
) -> None:
    """Append one completed-candle research snapshot without mutating prior evidence."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO research_evidence("
            "observed_at_utc, symbol, candle_open_utc, window_hours, chart_structure, calendar_state, "
            "consensus_state, source_statuses_json"
            ") VALUES (?, ?, ?, 12, ?, ?, ?, ?) "
            "ON CONFLICT(symbol, candle_open_utc, window_hours) DO NOTHING",
            (
                observed_at_utc.isoformat(), symbol, candle_open_utc.isoformat(), chart_structure,
                calendar_state, consensus_state, json.dumps(source_statuses, sort_keys=True),
            ),
        )
        connection.commit()


def count_research_evidence(path: Path, symbol: str | None = None) -> int:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        if symbol:
            row = connection.execute("SELECT COUNT(*) FROM research_evidence WHERE symbol = ?", (symbol,)).fetchone()
        else:
            row = connection.execute("SELECT COUNT(*) FROM research_evidence").fetchone()
    return int(row[0]) if row else 0


def write_calendar_cache(path: Path, provider: str, fetched_at_utc: datetime, payload: dict[str, Any]) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO calendar_cache(provider, fetched_at_utc, payload_json) VALUES (?, ?, ?) "
            "ON CONFLICT(provider) DO UPDATE SET fetched_at_utc=excluded.fetched_at_utc, payload_json=excluded.payload_json",
            (provider, fetched_at_utc.isoformat(), json.dumps(payload)),
        )
        connection.commit()


def read_calendar_cache(path: Path, provider: str) -> tuple[datetime, dict[str, Any]] | None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT fetched_at_utc, payload_json FROM calendar_cache WHERE provider = ?",
            (provider,),
        ).fetchone()
    if not row:
        return None
    return datetime.fromisoformat(row[0]), json.loads(row[1])


def record_backtest_run(
    path: Path,
    *,
    run_id: str,
    created_at_utc: datetime,
    symbol: str,
    timeframe: str,
    dataset_start_utc: datetime | None,
    dataset_end_utc: datetime | None,
    completed_candles: int,
    data_status: str,
    reason_codes: list[str],
    payload: dict[str, Any],
) -> None:
    """Persist an immutable summary of a completed research run."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO backtest_runs("
            "run_id, created_at_utc, symbol, timeframe, dataset_start_utc, dataset_end_utc, completed_candles, "
            "data_status, reason_codes_json, payload_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, created_at_utc.isoformat(), symbol, timeframe,
                dataset_start_utc.isoformat() if dataset_start_utc else None,
                dataset_end_utc.isoformat() if dataset_end_utc else None,
                completed_candles, data_status, json.dumps(reason_codes), json.dumps(payload, sort_keys=True),
            ),
        )
        connection.commit()


def read_recent_backtest_runs(path: Path, limit: int = 10) -> list[dict[str, Any]]:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        records = connection.execute(
            "SELECT run_id, created_at_utc, symbol, timeframe, completed_candles, data_status, reason_codes_json "
            "FROM backtest_runs ORDER BY created_at_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            **{key: value for key, value in dict(record).items() if key != "reason_codes_json"},
            "reason_codes": json.loads(record["reason_codes_json"]),
        }
        for record in records
    ]


def store_completed_candles(
    path: Path,
    *,
    source: str,
    broker_server: str | None,
    symbol: str,
    timeframe: str,
    candles: list[Any],
    timeframe_seconds: int,
    observed_at_utc: datetime,
) -> int:
    """Persist only completed MT5 bars; conflicts preserve the first raw observation."""
    completed = [candle for candle in candles if candle.completed]
    if not completed:
        return 0
    initialize_database(path)
    normalized_broker_server = broker_server or ""
    values = [
        (
            source, normalized_broker_server, symbol, timeframe, candle.open_time_utc.isoformat(),
            (candle.open_time_utc.timestamp() + timeframe_seconds),
            candle.open, candle.high, candle.low, candle.close, candle.tick_volume,
            candle.real_volume, candle.spread_points, observed_at_utc.isoformat(),
            (candle.raw_open_time_utc or candle.open_time_utc).isoformat(),
            candle.broker_clock_offset_seconds, int(candle.timestamp_normalized),
        )
        for candle in completed
    ]
    with sqlite3.connect(path) as connection:
        before = connection.total_changes
        connection.executemany(
            "INSERT INTO market_candles("
            "source, broker_server, symbol, timeframe, open_time_utc, close_time_utc, open, high, low, close, "
            "tick_volume, real_volume, spread_points, observed_at_utc, raw_open_time_utc, "
            "broker_clock_offset_seconds, timestamp_normalized"
            ") VALUES (?, ?, ?, ?, ?, datetime(?, 'unixepoch'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source, broker_server, symbol, timeframe, open_time_utc) DO NOTHING",
            values,
        )
        connection.commit()
        return connection.total_changes - before


def read_completed_candles(
    path: Path,
    *,
    symbol: str,
    timeframe: str,
    limit: int,
    source: str = "MT5",
    broker_server: str | None = None,
) -> list[Any]:
    """Read source-backed completed bars in chronological order."""
    from app.schemas.market import Candle

    initialize_database(path)
    broker_filter = " AND broker_server = ?" if broker_server is not None else ""
    parameters: tuple[Any, ...] = (source, symbol, timeframe, *( [broker_server] if broker_server is not None else []), limit)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        records = connection.execute(
            "SELECT open_time_utc, open, high, low, close, tick_volume, real_volume, spread_points, source, "
            "raw_open_time_utc, broker_clock_offset_seconds, timestamp_normalized "
            "FROM market_candles WHERE source = ? AND symbol = ? AND timeframe = ? "
            f"{broker_filter} ORDER BY open_time_utc DESC LIMIT ?",
            parameters,
        ).fetchall()
    return [
        Candle(
            open_time_utc=datetime.fromisoformat(row["open_time_utc"]),
            open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
            tick_volume=int(row["tick_volume"]), real_volume=row["real_volume"],
            spread_points=row["spread_points"], completed=True, source=row["source"],
            raw_open_time_utc=datetime.fromisoformat(row["raw_open_time_utc"]) if row["raw_open_time_utc"] else None,
            broker_clock_offset_seconds=int(row["broker_clock_offset_seconds"]),
            timestamp_normalized=bool(row["timestamp_normalized"]),
        )
        for row in reversed(records)
    ]


def count_completed_candles(
    path: Path,
    *,
    symbol: str,
    timeframe: str,
    source: str = "MT5",
    broker_server: str | None = None,
) -> int:
    initialize_database(path)
    broker_filter = " AND broker_server = ?" if broker_server is not None else ""
    parameters: tuple[Any, ...] = (source, symbol, timeframe, *( [broker_server] if broker_server is not None else []))
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM market_candles WHERE source = ? AND symbol = ? AND timeframe = ?"
            f"{broker_filter}",
            parameters,
        ).fetchone()
    return int(row[0]) if row else 0


def read_completed_archive_coverage(
    path: Path,
    *,
    symbol: str | None,
    broker_server: str | None,
) -> list[dict[str, Any]]:
    """Read the current broker archive without mixing in another broker's history."""
    if not symbol:
        return []
    initialize_database(path)
    normalized_broker_server = broker_server or ""
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT source, broker_server, symbol, timeframe, COUNT(*) AS completed_candles, "
            "MIN(open_time_utc) AS first_open_utc, MAX(open_time_utc) AS latest_open_utc "
            "FROM market_candles WHERE source = 'MT5' AND symbol = ? AND broker_server = ? "
            "GROUP BY source, broker_server, symbol, timeframe ORDER BY timeframe",
            (symbol, normalized_broker_server),
        ).fetchall()
    coverage: list[dict[str, Any]] = []
    for row in rows:
        first = datetime.fromisoformat(row["first_open_utc"])
        latest = datetime.fromisoformat(row["latest_open_utc"])
        span_days = max((latest - first).total_seconds() / 86_400, 0.0)
        count = int(row["completed_candles"])
        if row["timeframe"] == "M5" and count >= 5_000 and span_days >= 90:
            readiness, reasons = "WALK_FORWARD_READY", ["M5_COUNT_AND_90_DAY_SPAN_MET"]
        elif count:
            readiness, reasons = "COLLECTING", ["HISTORY_TARGET_NOT_YET_MET"]
        else:
            readiness, reasons = "INSUFFICIENT", ["NO_COMPLETED_ARCHIVE"]
        coverage.append({
            "source": row["source"], "broker_server": row["broker_server"] or None,
            "symbol": row["symbol"], "timeframe": row["timeframe"], "completed_candles": count,
            "first_open_utc": first, "latest_open_utc": latest, "observed_span_days": span_days,
            "readiness": readiness, "reason_codes": reasons,
        })
    return coverage


def enqueue_research_job(
    path: Path,
    *,
    job_id: str,
    job_type: str,
    symbol: str,
    anchor_time_utc: datetime,
    created_at_utc: datetime,
    payload: dict[str, Any],
) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO research_jobs("
            "job_id, job_type, symbol, anchor_time_utc, state, created_at_utc, reason_codes_json, payload_json"
            ") VALUES (?, ?, ?, ?, 'QUEUED', ?, '[]', ?) "
            "ON CONFLICT(job_type, symbol, anchor_time_utc) DO NOTHING",
            (
                job_id, job_type, symbol, anchor_time_utc.isoformat(), created_at_utc.isoformat(),
                json.dumps(payload, sort_keys=True),
            ),
        )
        connection.commit()


def claim_next_research_job(path: Path) -> dict[str, Any] | None:
    """Claim exactly one durable job so interrupted jobs can be recovered safely."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE")
        record = connection.execute(
            "SELECT job_id, job_type, symbol, anchor_time_utc, payload_json FROM research_jobs "
            "WHERE state = 'QUEUED' ORDER BY created_at_utc ASC LIMIT 1"
        ).fetchone()
        if not record:
            connection.commit()
            return None
        updated = connection.execute(
            "UPDATE research_jobs SET state = 'RUNNING', started_at_utc = strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "attempt_count = attempt_count + 1 WHERE job_id = ? AND state = 'QUEUED'",
            (record["job_id"],),
        ).rowcount
        connection.commit()
    if updated != 1:
        return None
    return {
        "job_id": record["job_id"],
        "job_type": record["job_type"],
        "symbol": record["symbol"],
        "anchor_time_utc": datetime.fromisoformat(record["anchor_time_utc"]),
        "payload": json.loads(record["payload_json"]),
    }


def complete_research_job(path: Path, *, job_id: str, reason_codes: list[str]) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE research_jobs SET state = 'COMPLETED', completed_at_utc = strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "reason_codes_json = ? WHERE job_id = ?",
            (json.dumps(reason_codes), job_id),
        )
        connection.commit()


def fail_research_job(path: Path, *, job_id: str, reason_codes: list[str]) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE research_jobs SET state = 'FAILED', completed_at_utc = strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "reason_codes_json = ? WHERE job_id = ?",
            (json.dumps(reason_codes), job_id),
        )
        connection.commit()


def recover_interrupted_research_jobs(path: Path) -> int:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        changed = connection.execute(
            "UPDATE research_jobs SET state = 'QUEUED', started_at_utc = NULL "
            "WHERE state = 'RUNNING'"
        ).rowcount
        connection.commit()
    return changed


def record_research_run(
    path: Path,
    *,
    run_id: str,
    job_id: str,
    observed_at_utc: datetime,
    symbol: str,
    anchor_time_utc: datetime,
    trigger: str,
    data_status: str,
    feature_set_version: str,
    source_statuses: dict[str, str],
    response: dict[str, Any],
    reason_codes: list[str],
) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO research_runs("
            "run_id, job_id, observed_at_utc, symbol, anchor_time_utc, trigger, data_status, feature_set_version, "
            "source_statuses_json, response_json, reason_codes_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id, job_id, observed_at_utc.isoformat(), symbol, anchor_time_utc.isoformat(), trigger,
                data_status, feature_set_version, json.dumps(source_statuses, sort_keys=True),
                json.dumps(response, sort_keys=True), json.dumps(reason_codes),
            ),
        )
        connection.commit()


def record_outcome_label(
    path: Path,
    *,
    run_id: str,
    label_version: str,
    horizon_bars: int,
    anchor_close: float,
    outcome_close: float,
    labelled_at_utc: datetime,
) -> None:
    delta = outcome_close - anchor_close
    direction = "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT"
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO research_labels("
            "run_id, label_version, horizon_bars, anchor_close, outcome_close, outcome_price_delta, direction, labelled_at_utc"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id, label_version, horizon_bars) DO NOTHING",
            (
                run_id, label_version, horizon_bars, anchor_close, outcome_close,
                delta, direction, labelled_at_utc.isoformat(),
            ),
        )
        connection.commit()


def read_unlabelled_research_runs(
    path: Path,
    *,
    symbol: str,
    label_version: str,
    horizon_bars: int,
    limit: int = 1_000,
) -> list[dict[str, Any]]:
    """Return durable completed-candle research runs that can still be outcome-labelled."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        records = connection.execute(
            "SELECT run_id, anchor_time_utc FROM research_runs AS run "
            "WHERE symbol = ? AND NOT EXISTS ("
            "SELECT 1 FROM research_labels AS label "
            "WHERE label.run_id = run.run_id AND label.label_version = ? AND label.horizon_bars = ?"
            ") ORDER BY anchor_time_utc ASC LIMIT ?",
            (symbol, label_version, horizon_bars, limit),
        ).fetchall()
    return [
        {"run_id": record["run_id"], "anchor_time_utc": datetime.fromisoformat(record["anchor_time_utc"])}
        for record in records
    ]


def record_calendar_snapshot(
    path: Path,
    *,
    snapshot_id: str,
    observed_at_utc: datetime,
    source: str,
    source_url: str,
    source_timestamp_utc: datetime | None,
    data_status: str,
    reason_codes: list[str],
    payload: dict[str, Any],
) -> None:
    """Persist the exact public-calendar response used by a research run."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO calendar_snapshots("
            "snapshot_id, observed_at_utc, source, source_url, source_timestamp_utc, data_status, "
            "reason_codes_json, payload_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                snapshot_id, observed_at_utc.isoformat(), source, source_url,
                source_timestamp_utc.isoformat() if source_timestamp_utc else None,
                data_status, json.dumps(reason_codes), json.dumps(payload, sort_keys=True),
            ),
        )
        connection.commit()


def record_model_version(
    path: Path,
    *,
    model_version_id: str,
    created_at_utc: datetime,
    model_kind: str,
    model_version: str,
    state: str,
    symbol: str,
    timeframe: str,
    dataset_start_utc: datetime | None,
    dataset_end_utc: datetime | None,
    dataset_candles: int,
    feature_set_version: str,
    metrics: dict[str, Any],
    payload: dict[str, Any],
    reason_codes: list[str],
) -> None:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO model_versions("
            "model_version_id, created_at_utc, model_kind, model_version, state, symbol, timeframe, "
            "dataset_start_utc, dataset_end_utc, dataset_candles, feature_set_version, metrics_json, payload_json, "
            "reason_codes_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                model_version_id, created_at_utc.isoformat(), model_kind, model_version, state, symbol, timeframe,
                dataset_start_utc.isoformat() if dataset_start_utc else None,
                dataset_end_utc.isoformat() if dataset_end_utc else None,
                dataset_candles, feature_set_version, json.dumps(metrics, sort_keys=True),
                json.dumps(payload, sort_keys=True), json.dumps(reason_codes),
            ),
        )
        connection.commit()


def read_operations_status(path: Path) -> dict[str, Any]:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        controls = dict(connection.execute("SELECT key, value FROM research_operations_controls").fetchall())
        latest_audit = connection.execute(
            "SELECT occurred_at_utc FROM research_operations_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        today_failures = connection.execute(
            "SELECT COUNT(*) FROM research_jobs WHERE state = 'FAILED' "
            "AND date(created_at_utc) = date('now')"
        ).fetchone()
    kill_switch = controls.get("paper_kill_switch", "false").lower() == "true"
    failures = int(today_failures[0]) if today_failures else 0
    alerts: list[str] = []
    if kill_switch:
        alerts.append("PAPER_KILL_SWITCH_ENABLED")
    if failures:
        alerts.append("RESEARCH_JOB_FAILURES_TODAY")
    return {
        "kill_switch_enabled": kill_switch,
        "model_promotion_state": controls.get("model_promotion_state", "REVIEW_REQUIRED"),
        "daily_research_failure_count": failures,
        "alerts": alerts,
        "latest_audit_at_utc": datetime.fromisoformat(latest_audit[0]) if latest_audit else None,
        "reason_codes": ["NO_ORDER_EXECUTION", "MANUAL_PROMOTION_REQUIRED"],
    }


def write_operation_control(path: Path, *, key: str, value: str, actor: str, action: str) -> None:
    initialize_database(path)
    now = datetime.now(UTC)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO research_operations_controls(key, value, updated_at_utc) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at_utc=excluded.updated_at_utc",
            (key, value, now.isoformat()),
        )
        connection.execute(
            "INSERT INTO research_operations_audit(occurred_at_utc, actor, action, payload_json) VALUES (?, ?, ?, ?)",
            (now.isoformat(), actor, action, json.dumps({"key": key, "value": value}, sort_keys=True)),
        )
        connection.commit()


def record_broker_session_state(path: Path, *, symbol: str | None, state: str, observed_at_utc: datetime) -> bool:
    """Record state transitions only; repeated polling never manufactures a change."""
    if not symbol:
        return False
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        previous = connection.execute(
            "SELECT current_state FROM broker_session_transitions WHERE symbol = ? "
            "ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if previous is None:
            connection.execute(
                "INSERT INTO broker_session_transitions(symbol, previous_state, current_state, observed_at_utc) "
                "VALUES (?, 'INITIAL', ?, ?)",
                (symbol, state, observed_at_utc.isoformat()),
            )
            connection.commit()
            return False
        if previous[0] == state:
            return False
        connection.execute(
            "INSERT INTO broker_session_transitions(symbol, previous_state, current_state, observed_at_utc) "
            "VALUES (?, ?, ?, ?)",
            (symbol, previous[0], state, observed_at_utc.isoformat()),
        )
        connection.commit()
    return True


def record_frozen_research_decision(
    path: Path,
    *,
    decision_id: str,
    observed_at_utc: datetime,
    symbol: str,
    anchor_time_utc: datetime,
    decision: str,
    feature_set_version: str,
    input_fingerprint: str,
    quote_source_timestamp_utc: datetime | None,
    quote_bid: float | None,
    quote_ask: float | None,
    spread_points: float | None,
    data_quality_state: str,
    event_risk_state: str,
    session_regime: str,
    model_promotion_state: str,
    paper_status: str,
    feature_snapshot: dict[str, Any],
    ensemble: dict[str, Any],
    costs: dict[str, Any],
    reason_codes: list[str],
) -> bool:
    """Freeze a decision-time input snapshot. Conflicts preserve the first record."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        changed = connection.execute(
            "INSERT INTO frozen_research_decisions("
            "decision_id, observed_at_utc, symbol, anchor_time_utc, decision, feature_set_version, input_fingerprint, "
            "quote_source_timestamp_utc, quote_bid, quote_ask, spread_points, data_quality_state, event_risk_state, "
            "session_regime, model_promotion_state, paper_status, feature_snapshot_json, ensemble_json, costs_json, reason_codes_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(symbol, anchor_time_utc, feature_set_version) DO NOTHING",
            (
                decision_id, observed_at_utc.isoformat(), symbol, anchor_time_utc.isoformat(), decision,
                feature_set_version, input_fingerprint,
                quote_source_timestamp_utc.isoformat() if quote_source_timestamp_utc else None,
                quote_bid, quote_ask, spread_points, data_quality_state, event_risk_state, session_regime,
                model_promotion_state, paper_status, json.dumps(feature_snapshot, sort_keys=True),
                json.dumps(ensemble, sort_keys=True), json.dumps(costs, sort_keys=True), json.dumps(reason_codes),
            ),
        ).rowcount
        connection.commit()
    return changed == 1


def record_strategy_journal_events(
    path: Path,
    *,
    observed_at_utc: datetime,
    symbol: str,
    candle_open_utc: datetime,
    disposition: str,
    modules: list[dict[str, Any]],
) -> int:
    """Append module outcomes without rewriting earlier decision-time evidence."""
    from uuid import uuid4

    initialize_database(path)
    inserted = 0
    with sqlite3.connect(path) as connection:
        for module in modules:
            inserted += connection.execute(
                "INSERT INTO strategy_journal_events("
                "event_id, occurred_at_utc, symbol, candle_open_utc, strategy_id, strategy_version, state, direction, "
                "disposition, data_sources_json, reason_codes_json, evidence_json"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(symbol, candle_open_utc, strategy_id, strategy_version, state) DO NOTHING",
                (
                    str(uuid4()), observed_at_utc.isoformat(), symbol, candle_open_utc.isoformat(),
                    str(module["strategy_id"]), str(module["strategy_version"]), str(module["state"]),
                    str(module["direction"]), disposition,
                    json.dumps(module.get("data_sources", []), sort_keys=True),
                    json.dumps(module.get("reason_codes", []), sort_keys=True), json.dumps(module, sort_keys=True),
                ),
            ).rowcount
        connection.commit()
    return inserted


def read_recent_strategy_journal_events(path: Path, *, symbol: str | None, limit: int = 40) -> list[dict[str, Any]]:
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        clause = "WHERE symbol = ?" if symbol else ""
        rows = connection.execute(
            "SELECT event_id, occurred_at_utc, symbol, candle_open_utc, strategy_id, strategy_version, state, direction, "
            "disposition, data_sources_json, reason_codes_json FROM strategy_journal_events "
            f"{clause} ORDER BY occurred_at_utc DESC, event_id DESC LIMIT ?",
            ((symbol, limit) if symbol else (limit,)),
        ).fetchall()
    return [
        {
            "event_id": row["event_id"], "occurred_at_utc": datetime.fromisoformat(row["occurred_at_utc"]),
            "symbol": row["symbol"], "candle_open_utc": datetime.fromisoformat(row["candle_open_utc"]),
            "strategy_id": row["strategy_id"], "strategy_version": row["strategy_version"],
            "state": row["state"], "direction": row["direction"], "disposition": row["disposition"],
            "data_sources": json.loads(row["data_sources_json"]), "reason_codes": json.loads(row["reason_codes_json"]),
        }
        for row in rows
    ]


def read_recent_model_versions(path: Path, *, symbol: str | None, limit: int = 20) -> list[dict[str, Any]]:
    """List the local research registry without exposing serialized artifacts."""
    initialize_database(path)
    where = "WHERE invalidated_at_utc IS NULL"
    parameters: tuple[Any, ...] = ()
    if symbol:
        where += " AND symbol = ?"
        parameters = (symbol,)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT model_version_id, created_at_utc, model_kind, model_version, state, symbol, timeframe, "
            "dataset_start_utc, dataset_end_utc, dataset_candles, feature_set_version, reason_codes_json "
            f"FROM model_versions {where} ORDER BY created_at_utc DESC, model_version_id DESC LIMIT ?",
            (*parameters, limit),
        ).fetchall()
    return [
        {
            "model_version_id": row["model_version_id"],
            "created_at_utc": datetime.fromisoformat(row["created_at_utc"]),
            "model_kind": row["model_kind"],
            "model_version": row["model_version"],
            "state": row["state"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "dataset_start_utc": datetime.fromisoformat(row["dataset_start_utc"]) if row["dataset_start_utc"] else None,
            "dataset_end_utc": datetime.fromisoformat(row["dataset_end_utc"]) if row["dataset_end_utc"] else None,
            "dataset_candles": int(row["dataset_candles"]),
            "feature_set_version": row["feature_set_version"],
            "reason_codes": json.loads(row["reason_codes_json"]),
        }
        for row in rows
    ]


def label_mature_frozen_decisions(
    path: Path,
    *,
    symbol: str,
    candles: list[Any],
    horizon_bars: int,
    label_version: str,
    labelled_at_utc: datetime,
) -> int:
    """Attach fixed-horizon outcome labels only after future completed bars exist."""
    initialize_database(path)
    candle_by_time = {candle.open_time_utc: (index, candle) for index, candle in enumerate(candles)}
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        pending = connection.execute(
            "SELECT decision_id, anchor_time_utc, decision FROM frozen_research_decisions AS decision "
            "WHERE symbol = ? AND decision != 'NO_TRADE' AND NOT EXISTS ("
            "SELECT 1 FROM paper_decision_labels AS label WHERE label.decision_id = decision.decision_id "
            "AND label.label_version = ? AND label.horizon_bars = ?"
            ") ORDER BY anchor_time_utc ASC",
            (symbol, label_version, horizon_bars),
        ).fetchall()
        inserted = 0
        for row in pending:
            entry = candle_by_time.get(datetime.fromisoformat(row["anchor_time_utc"]))
            if not entry:
                continue
            index, anchor = entry
            if index + horizon_bars >= len(candles):
                continue
            outcome = candles[index + horizon_bars]
            delta = outcome.close - anchor.close
            decision = row["decision"]
            match = (decision == "WATCH_LONG" and delta > 0) or (decision == "WATCH_SHORT" and delta < 0)
            result = connection.execute(
                "INSERT INTO paper_decision_labels("
                "decision_id, label_version, horizon_bars, anchor_close, outcome_close, outcome_price_delta, directional_match, labelled_at_utc"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(decision_id, label_version, horizon_bars) DO NOTHING",
                (
                    row["decision_id"], label_version, horizon_bars, anchor.close, outcome.close,
                    delta, int(match), labelled_at_utc.isoformat(),
                ),
            ).rowcount
            inserted += result
        connection.commit()
    return inserted


def read_validation_summary(path: Path, *, symbol: str | None) -> dict[str, Any]:
    initialize_database(path)
    clauses = ["decision != 'NO_TRADE'"]
    params: list[Any] = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    where = " WHERE " + " AND ".join(clauses)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        total = connection.execute(
            "SELECT COUNT(*) FROM frozen_research_decisions" + (" WHERE symbol = ?" if symbol else ""),
            (symbol,) if symbol else (),
        ).fetchone()[0]
        candidates = connection.execute("SELECT COUNT(*) FROM frozen_research_decisions" + where, params).fetchone()[0]
        labelled = connection.execute(
            "SELECT decision.decision, decision.session_regime, label.directional_match, label.outcome_price_delta "
            "FROM frozen_research_decisions AS decision JOIN paper_decision_labels AS label "
            "ON label.decision_id = decision.decision_id" + where + " ORDER BY decision.anchor_time_utc ASC",
            params,
        ).fetchall()
    matches = sum(int(row["directional_match"] or 0) for row in labelled)
    count = len(labelled)
    accuracy = round(matches / count * 100, 2) if count >= 30 else None
    regimes: dict[str, int] = {}
    for row in labelled:
        regimes[row["session_regime"]] = regimes.get(row["session_regime"], 0) + 1
    split_one = int(count * 0.60)
    split_two = int(count * 0.80)
    walk_forward = {
        "training_labels": split_one,
        "validation_labels": split_two - split_one,
        "held_out_labels": count - split_two,
        "held_out_directional_matches": sum(int(row["directional_match"] or 0) for row in labelled[split_two:]),
    }
    return {
        "symbol": symbol,
        "total_frozen_decisions": int(total),
        "paper_candidates": int(candidates),
        "labelled_candidates": count,
        "directional_matches": matches,
        "accuracy_percent": accuracy,
        "calibration_state": "REVIEW_REQUIRED" if count >= 30 else "INSUFFICIENT_LABELS",
        "walk_forward": walk_forward,
        "regime_counts": regimes,
        "maximum_drawdown_points": None,
        "cost_status": "COSTS_INCOMPLETE",
        "reason_codes": [
            "CHRONOLOGICAL_LABELS_ONLY", "HELD_OUT_NOT_USED_FOR_PROMOTION",
            "COMMISSION_AND_SLIPPAGE_UNAVAILABLE", "MANUAL_PROMOTION_REQUIRED", "NO_ORDER_EXECUTION",
        ],
    }


def read_pipeline_summary(path: Path, *, symbol: str | None) -> dict[str, Any]:
    """Expose persisted worker health without treating stale research as live market data."""
    initialize_database(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        job_rows = connection.execute(
            "SELECT state, COUNT(*) AS count FROM research_jobs GROUP BY state"
        ).fetchall()
        conditions = (symbol,) if symbol else ()
        where = "WHERE invalidated_at_utc IS NULL" + (" AND symbol = ?" if symbol else "")
        latest_run = connection.execute(
            "SELECT observed_at_utc, anchor_time_utc, data_status, reason_codes_json "
            f"FROM research_runs {where} ORDER BY observed_at_utc DESC LIMIT 1",
            conditions,
        ).fetchone()
        latest_model = connection.execute(
            "SELECT created_at_utc, model_kind, model_version, state, dataset_candles, reason_codes_json "
            f"FROM model_versions {where} ORDER BY created_at_utc DESC LIMIT 1",
            conditions,
        ).fetchone()
    return {
        "jobs": {record["state"]: int(record["count"]) for record in job_rows},
        "latest_run": (
            {
                "observed_at_utc": latest_run["observed_at_utc"],
                "anchor_time_utc": latest_run["anchor_time_utc"],
                "data_status": latest_run["data_status"],
                "reason_codes": json.loads(latest_run["reason_codes_json"]),
            }
            if latest_run else None
        ),
        "latest_model": (
            {
                "created_at_utc": latest_model["created_at_utc"],
                "model_kind": latest_model["model_kind"],
                "model_version": latest_model["model_version"],
                "state": latest_model["state"],
                "dataset_candles": int(latest_model["dataset_candles"]),
                "reason_codes": json.loads(latest_model["reason_codes_json"]),
            }
            if latest_model else None
        ),
    }


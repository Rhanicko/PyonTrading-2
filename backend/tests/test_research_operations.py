from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import routes
from app.analysis.quality import assess_data_quality, classify_session_and_regime
from app.schemas.market import Candle, DataStatus, QuoteResponse
from app.storage.database import (
    label_mature_frozen_decisions,
    record_broker_session_state,
    read_operations_status,
    read_validation_summary,
    record_frozen_research_decision,
    write_operation_control,
)


def _candle(index: int) -> Candle:
    start = datetime(2026, 10, 22, tzinfo=UTC)
    return Candle(
        open_time_utc=start + timedelta(minutes=index * 5), open=4100 + index,
        high=4101 + index, low=4099 + index, close=4100.5 + index,
        tick_volume=10, spread_points=30, completed=True,
    )


def test_integrity_reports_gap_and_regime_without_tzdata_crash():
    quote = QuoteResponse(
        observed_at_utc=datetime.now(UTC), source_timestamp_utc=datetime.now(UTC),
        data_status=DataStatus.LIVE, symbol="XAUUSD", bid=4200, ask=4200.3,
        spread_points=30,
    )
    candles = [_candle(index) for index in range(40)]
    quality = assess_data_quality(quote, candles, timeframe=timedelta(minutes=5))
    assert quality.status == "CLEAR"
    assert quality.candle_gap_count == 0

    gapped = [*candles]
    gapped[-1] = gapped[-1].model_copy(update={"open_time_utc": gapped[-2].open_time_utc + timedelta(minutes=15)})
    watched = assess_data_quality(quote, gapped, timeframe=timedelta(minutes=5))
    assert watched.status == "WATCH"
    assert "CANDLE_GAPS_DETECTED" in watched.reason_codes
    regime = classify_session_and_regime(candles, structure="UPWARD_STRUCTURE", spread_state="NORMAL")
    assert regime.market_regime == "TREND"


def test_frozen_paper_candidates_are_labelled_only_after_future_completed_bars(tmp_path):
    database = tmp_path / "research.db"
    anchor = _candle(0).open_time_utc
    assert record_frozen_research_decision(
        database,
        decision_id="paper-1", observed_at_utc=anchor, symbol="XAUUSD", anchor_time_utc=anchor,
        decision="WATCH_LONG", feature_set_version="research-v3", input_fingerprint="a" * 64,
        quote_source_timestamp_utc=anchor, quote_bid=4100, quote_ask=4100.3, spread_points=30,
        data_quality_state="CLEAR", event_risk_state="UPCOMING_USD_EVENT", session_regime="TREND",
        model_promotion_state="REVIEW_REQUIRED", paper_status="RECORDED", feature_snapshot={}, ensemble={},
        costs={"spread_points": 30, "commission_points": None, "slippage_points": None},
        reason_codes=["NO_ORDER_EXECUTION"],
    )
    assert label_mature_frozen_decisions(
        database, symbol="XAUUSD", candles=[_candle(index) for index in range(13)],
        horizon_bars=12, label_version="paper-v1", labelled_at_utc=anchor + timedelta(hours=1),
    ) == 1
    summary = read_validation_summary(database, symbol="XAUUSD")
    assert summary["paper_candidates"] == 1
    assert summary["labelled_candidates"] == 1
    assert summary["directional_matches"] == 1
    assert summary["accuracy_percent"] is None
    assert summary["calibration_state"] == "INSUFFICIENT_LABELS"


def test_paper_kill_switch_is_persistent_and_audited(tmp_path):
    database = tmp_path / "research.db"
    assert not read_operations_status(database)["kill_switch_enabled"]
    write_operation_control(
        database, key="paper_kill_switch", value="true", actor="TEST_OPERATOR", action="PAPER_KILL_SWITCH_UPDATED",
    )
    status = read_operations_status(database)
    assert status["kill_switch_enabled"]
    assert "PAPER_KILL_SWITCH_ENABLED" in status["alerts"]
    assert status["latest_audit_at_utc"] is not None


def test_broker_session_transition_is_only_recorded_when_state_changes(tmp_path):
    database = tmp_path / "research.db"
    now = datetime.now(UTC)
    assert not record_broker_session_state(database, symbol="XAUUSD", state="LIVE_QUOTE", observed_at_utc=now)
    assert not record_broker_session_state(database, symbol="XAUUSD", state="LIVE_QUOTE", observed_at_utc=now + timedelta(seconds=30))
    assert record_broker_session_state(database, symbol="XAUUSD", state="STALE_OR_CLOSED", observed_at_utc=now + timedelta(minutes=1))


def test_operator_guard_rejects_missing_or_incorrect_strategy_control_token(monkeypatch):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(operator_token="test-operator-token"))

    routes.require_operator_token("test-operator-token")
    with pytest.raises(HTTPException) as missing:
        routes.require_operator_token(None)
    with pytest.raises(HTTPException) as incorrect:
        routes.require_operator_token("wrong-token")

    assert missing.value.status_code == 403
    assert incorrect.value.status_code == 403

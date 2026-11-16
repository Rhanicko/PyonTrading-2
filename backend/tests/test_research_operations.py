from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import routes
from app.analysis.quality import assess_data_quality, classify_session_and_regime
from app.schemas.market import Candle, DataStatus, QuoteResponse
from app.services.pipeline import ResearchPipeline
from app.storage.database import (
    label_mature_frozen_decisions,
    record_broker_session_state,
    read_operations_status,
    read_validation_summary,
    record_frozen_research_decision,
    record_research_run,
    record_signal_history,
    write_operation_control,
)


def test_research_controller_requires_operator_token_and_persists_pause(tmp_path, monkeypatch):
    database = tmp_path / "research.db"
    app = FastAPI()
    app.include_router(routes.router)
    app.state.database_path = database
    app.state.research_pipeline = ResearchPipeline(
        adapter=SimpleNamespace(), calendar=SimpleNamespace(), coordinator=SimpleNamespace(),
        database_path=database, configured_symbol=lambda: "XAUUSD",
    )
    monkeypatch.setattr(routes, "settings", SimpleNamespace(operator_token="test-operator-token"))

    with TestClient(app) as client:
        assert client.post("/api/research/pipeline/control", json={"enabled": False}).status_code == 403
        assert client.post("/api/research/pipeline/control", json={"enabled": False}, headers={"X-Pyon-Operator-Token": "wrong"}).status_code == 403
        response = client.post("/api/research/pipeline/control", json={"enabled": False}, headers={"X-Pyon-Operator-Token": "test-operator-token"})
        assert response.status_code == 200
        assert response.json()["enabled"] is False
        assert read_operations_status(database)["research_pipeline_enabled"] is False
        assert read_operations_status(database)["latest_audit_at_utc"] is not None
        resumed = client.post("/api/research/pipeline/control", json={"enabled": True}, headers={"X-Pyon-Operator-Token": "test-operator-token"})
        assert resumed.status_code == 200
        assert resumed.json()["enabled"] is True


def test_health_distinguishes_service_readiness_from_closed_market_data():
    app = FastAPI()
    app.include_router(routes.router)
    now = datetime.now(UTC)
    app.state.live_service = SimpleNamespace(
        configured_symbol="XAUUSD",
        adapter=SimpleNamespace(
            connection=lambda _symbol: SimpleNamespace(
                source_timestamp_utc=None, data_status=DataStatus.LIVE,
                reason_codes=[], terminal_connected=True,
            ),
            quote=lambda _symbol: QuoteResponse(
                observed_at_utc=now, source_timestamp_utc=now - timedelta(hours=1),
                data_status=DataStatus.MARKET_CLOSED, symbol="XAUUSD",
                reason_codes=["WEEKEND_OR_MARKET_CLOSED"],
            ),
        ),
    )

    with TestClient(app) as client:
        payload = client.get("/api/health").json()

    assert payload["ready"] is True
    assert payload["readiness_scope"] == "HTTP_SERVICE"
    assert payload["market_data_status"] == "MARKET_CLOSED"
    assert payload["market_data_live"] is False


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


def test_monday_asian_session_is_not_labelled_weekend_from_utc_sunday():
    regime = classify_session_and_regime(
        [], structure="UNAVAILABLE", spread_state="NORMAL",
        now=datetime(2026, 11, 15, 23, 30, tzinfo=UTC),
    )
    assert regime.session_label == "ASIA"


def test_saturday_asian_clock_does_not_create_a_trading_session():
    regime = classify_session_and_regime(
        [], structure="UNAVAILABLE", spread_state="NORMAL",
        now=datetime(2026, 11, 14, 0, 30, tzinfo=UTC),
    )
    assert regime.session_label == "WEEKEND"


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
        horizon_bars=12, label_version="paper-candidate-direction-v2", labelled_at_utc=anchor + timedelta(hours=1),
    ) == 1
    summary = read_validation_summary(database, symbol="XAUUSD")
    assert summary["paper_candidates"] == 1
    assert summary["labelled_candidates"] == 1
    assert summary["directional_matches"] == 1
    assert summary["accuracy_percent"] is None
    assert summary["calibration_state"] == "INSUFFICIENT_LABELS"


def test_paper_candidate_is_not_labelled_across_a_missing_m5_bar(tmp_path):
    database = tmp_path / "research.db"
    anchor = _candle(0).open_time_utc
    record_frozen_research_decision(
        database,
        decision_id="paper-gap", observed_at_utc=anchor, symbol="XAUUSD", anchor_time_utc=anchor,
        decision="WATCH_LONG", feature_set_version="research-v3", input_fingerprint="b" * 64,
        quote_source_timestamp_utc=anchor, quote_bid=4100, quote_ask=4100.3, spread_points=30,
        data_quality_state="CLEAR", event_risk_state="UPCOMING_USD_EVENT", session_regime="TREND",
        model_promotion_state="REVIEW_REQUIRED", paper_status="RECORDED", feature_snapshot={}, ensemble={},
        costs={"spread_points": 30, "commission_points": None, "slippage_points": None},
        reason_codes=["NO_ORDER_EXECUTION"],
    )
    candles = [_candle(index if index < 6 else index + 1) for index in range(13)]

    assert label_mature_frozen_decisions(
        database, symbol="XAUUSD", candles=candles,
        horizon_bars=12, label_version="paper-v1", labelled_at_utc=anchor + timedelta(hours=2),
    ) == 0
    assert read_validation_summary(database, symbol="XAUUSD")["labelled_candidates"] == 0


def test_validation_ignores_legacy_paper_labels_after_continuity_version_change(tmp_path):
    database = tmp_path / "research.db"
    anchor = _candle(0).open_time_utc
    record_frozen_research_decision(
        database,
        decision_id="paper-legacy", observed_at_utc=anchor, symbol="XAUUSD", anchor_time_utc=anchor,
        decision="WATCH_LONG", feature_set_version="research-v3", input_fingerprint="c" * 64,
        quote_source_timestamp_utc=anchor, quote_bid=4100, quote_ask=4100.3, spread_points=30,
        data_quality_state="CLEAR", event_risk_state="UPCOMING_USD_EVENT", session_regime="TREND",
        model_promotion_state="REVIEW_REQUIRED", paper_status="RECORDED", feature_snapshot={}, ensemble={},
        costs={"spread_points": 30, "commission_points": None, "slippage_points": None},
        reason_codes=["NO_ORDER_EXECUTION"],
    )
    candles = [_candle(index) for index in range(13)]
    assert label_mature_frozen_decisions(
        database, symbol="XAUUSD", candles=candles,
        horizon_bars=12, label_version="paper-candidate-direction-v1", labelled_at_utc=anchor + timedelta(hours=1),
    ) == 1
    assert read_validation_summary(database, symbol="XAUUSD")["labelled_candidates"] == 0
    assert label_mature_frozen_decisions(
        database, symbol="XAUUSD", candles=candles,
        horizon_bars=12, label_version="paper-candidate-direction-v2", labelled_at_utc=anchor + timedelta(hours=1),
    ) == 1
    summary = read_validation_summary(database, symbol="XAUUSD")
    assert summary["labelled_candidates"] == 1
    assert summary["directional_matches"] == 1


def test_validation_audits_frozen_signal_proofs_without_calling_them_profitable(tmp_path):
    database = tmp_path / "research.db"
    anchor = _candle(0).open_time_utc
    for index, (symbol, state, failed) in enumerate((
        ("XAUUSD", "WITHHELD", "COMPLETED_MTF_ALIGNMENT"),
        ("XAUUSD", "ELIGIBLE", None),
        ("EURUSD", "WITHHELD", "CALENDAR_RISK_CHECKED"),
    )):
        record_research_run(
            database, run_id=f"run-{index}", job_id=f"job-{index}",
            observed_at_utc=anchor, symbol=symbol,
            anchor_time_utc=anchor + timedelta(minutes=5 * index),
            trigger="COMPLETED_M5_BAR", data_status="LIVE",
            feature_set_version="research-v3", source_statuses={"timeframe_M5": "LIVE"},
            response={"live_research_watch": {
                "lifecycle": "ACTIVE_RESEARCH_WATCH" if not failed else "WITHHELD",
                "signal_proof": {"publication_state": state, "checks": [
                    {"code": failed or "COMPLETED_MTF_ALIGNMENT", "passed": not failed},
                ]},
            }},
            reason_codes=[],
        )
    record_signal_history(
        database, signal_id="auto-one", provided_at_utc=anchor, symbol="XAUUSD",
        source="PYONTRADING2_LIVE_RESEARCH_WATCH", source_timestamp_utc=anchor,
        data_status="LIVE", analysis_mode="AUTOMATIC_RESEARCH_WATCH_V1",
        decision="WATCH_SHORT", market_context="DOWNWARD_STRUCTURE",
        summary="Research watch only", event_risk_state="CLEAR", paper_status="NOT_CREATED",
        input_fingerprint="a" * 64, reason_codes=["NO_ORDER_EXECUTION"], payload={},
    )

    audit = read_validation_summary(database, symbol="XAUUSD")["proof_audit"]
    assert audit["source"] == "LOCAL_FROZEN_RESEARCH_RUNS"
    assert audit["sampled_runs"] == 2
    assert audit["proof_evaluated_runs"] == 2
    assert audit["eligible_runs"] == 1
    assert audit["published_signals"] == 1
    assert audit["failed_checks"] == [{"code": "COMPLETED_MTF_ALIGNMENT", "runs": 1}]
    assert "NOT_PERFORMANCE_VALIDATION" in audit["reason_codes"]


def test_validation_proof_audit_has_an_explicit_empty_state(tmp_path):
    database = tmp_path / "empty.db"
    anchor = _candle(0).open_time_utc
    for index, response in enumerate(({}, {"live_research_watch": {"signal_proof": {"checks": []}}})):
        record_research_run(
            database, run_id=f"legacy-{index}", job_id=f"legacy-job-{index}",
            observed_at_utc=anchor, symbol="XAUUSD", anchor_time_utc=anchor + timedelta(minutes=5 * index),
            trigger="COMPLETED_M5_BAR", data_status="LIVE", feature_set_version="legacy-v1",
            source_statuses={}, response=response, reason_codes=[],
        )
    audit = read_validation_summary(database, symbol="XAUUSD")["proof_audit"]
    assert audit["sampled_runs"] == 2
    assert audit["proof_evaluated_runs"] == 0
    assert audit["published_signals"] == 0
    assert audit["latest_proof_anchor_utc"] is None
    assert "NO_PROOF_EVIDENCE_IN_SAMPLE" in audit["reason_codes"]


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

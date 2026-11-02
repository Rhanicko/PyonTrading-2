from datetime import UTC, datetime, timedelta

from app.market.freshness import data_status_for_tick, is_weekend_utc
from app.schemas.market import DataStatus


def test_freshness_transitions_are_timestamp_based():
    now = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
    assert data_status_for_tick(now - timedelta(seconds=2), now=now)[0] == DataStatus.LIVE
    assert data_status_for_tick(now - timedelta(seconds=9), now=now)[0] == DataStatus.DELAYED
    assert data_status_for_tick(now - timedelta(seconds=20), now=now)[0] == DataStatus.STALE


def test_future_broker_tick_is_not_treated_as_live():
    now = datetime(2026, 10, 21, 8, 0, tzinfo=UTC)
    status, age = data_status_for_tick(now + timedelta(minutes=3), now=now)
    assert status == DataStatus.SOURCE_ERROR
    assert age == -180


def test_weekend_is_not_misreported_as_live_session():
    assert is_weekend_utc(datetime(2026, 10, 24, tzinfo=UTC))


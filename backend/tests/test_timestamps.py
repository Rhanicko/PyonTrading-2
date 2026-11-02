from datetime import UTC, datetime, timedelta

from app.market.timestamps import normalize_broker_timestamp


def test_whole_hour_future_broker_clock_is_normalized_with_raw_provenance():
    observed = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
    normalized = normalize_broker_timestamp(observed + timedelta(hours=3, seconds=1), observed_at_utc=observed)

    assert normalized.normalized is True
    assert normalized.broker_clock_offset_seconds == 10_800
    assert normalized.raw_utc == observed + timedelta(hours=3, seconds=1)
    assert normalized.effective_utc == observed + timedelta(seconds=1)


def test_non_aligned_future_timestamp_remains_rejected_by_freshness_guard():
    observed = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
    normalized = normalize_broker_timestamp(observed + timedelta(minutes=17), observed_at_utc=observed)

    assert normalized.normalized is False
    assert normalized.broker_clock_offset_seconds == 0
    assert normalized.effective_utc == observed + timedelta(minutes=17)

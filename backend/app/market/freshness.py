from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.market import DataStatus


def data_status_for_tick(
    tick_time: datetime | None,
    *,
    now: datetime | None = None,
    delayed_seconds: int = 5,
    stale_seconds: int = 15,
    max_future_seconds: int = 60,
) -> tuple[DataStatus, float | None]:
    """Classify a broker tick without substituting another feed."""
    if tick_time is None:
        return DataStatus.SOURCE_ERROR, None
    current = now or datetime.now(UTC)
    age = (current - tick_time.astimezone(UTC)).total_seconds()
    if age < -max_future_seconds:
        return DataStatus.SOURCE_ERROR, age
    if age <= delayed_seconds:
        return DataStatus.LIVE, age
    if age <= stale_seconds:
        return DataStatus.DELAYED, age
    return DataStatus.STALE, age


def is_weekend_utc(now: datetime | None = None) -> bool:
    return (now or datetime.now(UTC)).weekday() >= 5


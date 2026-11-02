from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


MAX_FUTURE_SOURCE_SECONDS = 60
MIN_BROKER_CLOCK_OFFSET_SECONDS = 3_600
MAX_BROKER_CLOCK_OFFSET_SECONDS = 14 * 3_600
OFFSET_ALIGNMENT_TOLERANCE_SECONDS = 120


@dataclass(frozen=True)
class NormalizedTimestamp:
    raw_utc: datetime
    effective_utc: datetime
    broker_clock_offset_seconds: int
    normalized: bool


def normalize_broker_timestamp(raw_utc: datetime, *, observed_at_utc: datetime) -> NormalizedTimestamp:
    """Correct a demonstrably whole-hour broker-server clock offset without discarding provenance.

    MT5 normally returns UTC. Some terminals expose the broker's server clock as
    an epoch timestamp instead. We only correct a future timestamp when it is
    within two minutes of a whole-hour offset up to fourteen hours. The raw
    timestamp and signed offset remain available to every caller.
    """
    raw = raw_utc.astimezone(UTC)
    observed = observed_at_utc.astimezone(UTC)
    future_seconds = (raw - observed).total_seconds()
    if future_seconds <= MAX_FUTURE_SOURCE_SECONDS:
        return NormalizedTimestamp(raw, raw, 0, False)
    offset_seconds = int(round(future_seconds / MIN_BROKER_CLOCK_OFFSET_SECONDS)) * MIN_BROKER_CLOCK_OFFSET_SECONDS
    residual = abs(future_seconds - offset_seconds)
    if (
        MIN_BROKER_CLOCK_OFFSET_SECONDS <= offset_seconds <= MAX_BROKER_CLOCK_OFFSET_SECONDS
        and residual <= OFFSET_ALIGNMENT_TOLERANCE_SECONDS
    ):
        return NormalizedTimestamp(
            raw,
            raw - timedelta(seconds=offset_seconds),
            offset_seconds,
            True,
        )
    return NormalizedTimestamp(raw, raw, 0, False)

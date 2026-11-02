from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta, timezone
from threading import Lock
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.schemas.market import CalendarEvent, DataStatus, EventsResponse
from app.storage.database import read_calendar_cache, write_calendar_cache


FOREX_FACTORY_CALENDAR_PAGE = "https://www.forexfactory.com/calendar"
FOREX_FACTORY_PROVIDER = "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT"
MANILA_TIME = timezone(timedelta(hours=8), name="Asia/Manila")


class ForexFactoryCalendarAdapter:
    """Bounded reader for Forex Factory's public weekly JSON export.

    The export is treated as informational calendar data, never as a trading signal.
    """

    def __init__(self, source_url: str, ttl_seconds: int = 600, database_path: Path | None = None) -> None:
        self.source_url = source_url
        self.ttl_seconds = ttl_seconds
        self._cached: EventsResponse | None = None
        self._cached_at: datetime | None = None
        self._failure: EventsResponse | None = None
        self._retry_after: datetime | None = None
        self.database_path = database_path
        self._lock = Lock()

    def upcoming_usd_events(self, limit: int = 5, today_only: bool = False) -> EventsResponse:
        now = datetime.now(UTC)
        with self._lock:
            if self._cached and self._cached_at and (now - self._cached_at).total_seconds() < self.ttl_seconds:
                return self._filtered_response(self._cached, now, limit, today_only)
            if self._failure and self._retry_after and now < self._retry_after:
                return self._filtered_response(self._failure, now, limit, today_only)
            try:
                events = self._fetch_events()
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
                reason = self._reason_code(error)
                fallback = self._cached or self._read_persisted_cache()
                if fallback:
                    delayed = fallback.model_copy(update={
                        "observed_at_utc": now,
                        "data_status": DataStatus.DELAYED,
                        "reason_codes": ["CALENDAR_REFRESH_FAILED", reason],
                    })
                    self._failure = delayed
                    self._retry_after = now + timedelta(minutes=5)
                    return self._filtered_response(delayed, now, limit, today_only)
                failure = EventsResponse(
                    observed_at_utc=now,
                    data_status=DataStatus.SOURCE_ERROR,
                    reason_codes=["CALENDAR_FETCH_FAILED", reason],
                    source_url=FOREX_FACTORY_CALENDAR_PAGE,
                )
                self._failure = failure
                self._retry_after = now + timedelta(minutes=5)
                return failure
            result = EventsResponse(
                observed_at_utc=now,
                source_timestamp_utc=now,
                data_status=DataStatus.LIVE,
                source_url=FOREX_FACTORY_CALENDAR_PAGE,
                events=events,
            )
            self._cached = result
            self._cached_at = now
            self._failure = None
            self._retry_after = None
            self._write_persisted_cache(result)
            return self._filtered_response(result, now, limit, today_only)

    @staticmethod
    def _filtered_response(source: EventsResponse, now: datetime, limit: int, today_only: bool) -> EventsResponse:
        events = [event for event in source.events if event.event_time_utc >= now]
        if today_only:
            philippines_today = now.astimezone(MANILA_TIME).date()
            events = [event for event in events if event.event_time_manila.date() == philippines_today]
        events.sort(key=lambda event: event.event_time_utc)
        return source.model_copy(update={"observed_at_utc": now, "events": events[:limit]})

    def _fetch_events(self) -> list[CalendarEvent]:
        error: Exception | None = None
        for attempt in range(2):
            try:
                request = Request(self.source_url, headers={"Accept": "application/json", "User-Agent": "PyonTrading2/0.1 calendar-reader"})
                with urlopen(request, timeout=8) as response:  # nosec B310 - URL is an explicit local setting
                    payload: Any = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, list):
                    raise ValueError("CALENDAR_PAYLOAD_NOT_A_LIST")
                return [event for item in payload if (event := self._to_event(item)) is not None]
            except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as caught:
                error = caught
                if isinstance(caught, HTTPError) and caught.code == 429:
                    break
                if attempt == 0:
                    time.sleep(0.2)
        assert error is not None
        raise error

    @staticmethod
    def _to_event(item: Any) -> CalendarEvent | None:
        if not isinstance(item, dict) or item.get("country") != "USD" or not isinstance(item.get("title"), str):
            return None
        raw_date = item.get("date")
        if not isinstance(raw_date, str):
            return None
        try:
            event_time = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            return None
        if event_time.tzinfo is None:
            return None
        impact = item.get("impact") if item.get("impact") in {"High", "Medium", "Low"} else "Unknown"
        return CalendarEvent(
            title=item["title"].strip(), currency="USD", impact=impact,
            event_time_utc=event_time.astimezone(UTC),
            event_time_manila=event_time.astimezone(MANILA_TIME),
            forecast=item.get("forecast") or None, previous=item.get("previous") or None,
            actual=item.get("actual") or None, source_url=FOREX_FACTORY_CALENDAR_PAGE,
        )

    def _write_persisted_cache(self, response: EventsResponse) -> None:
        if not self.database_path or not response.source_timestamp_utc:
            return
        write_calendar_cache(
            self.database_path,
            FOREX_FACTORY_PROVIDER,
            response.source_timestamp_utc,
            {"events": [event.model_dump(mode="json") for event in response.events]},
        )

    def _read_persisted_cache(self) -> EventsResponse | None:
        if not self.database_path:
            return None
        stored = read_calendar_cache(self.database_path, FOREX_FACTORY_PROVIDER)
        if not stored:
            return None
        fetched_at_utc, payload = stored
        raw_events = payload.get("events")
        if not isinstance(raw_events, list):
            return None
        try:
            events = [CalendarEvent.model_validate(item) for item in raw_events]
        except ValueError:
            return None
        return EventsResponse(
            observed_at_utc=datetime.now(UTC),
            source_timestamp_utc=fetched_at_utc,
            data_status=DataStatus.DELAYED,
            source_url=FOREX_FACTORY_CALENDAR_PAGE,
            events=events,
        )

    @staticmethod
    def _reason_code(error: Exception) -> str:
        if isinstance(error, HTTPError):
            return f"CALENDAR_HTTP_{error.code}"
        if isinstance(error, TimeoutError):
            return "CALENDAR_TIMEOUT"
        if isinstance(error, json.JSONDecodeError):
            return "CALENDAR_INVALID_JSON"
        if isinstance(error, ValueError):
            return "CALENDAR_INVALID_PAYLOAD"
        return "CALENDAR_NETWORK_ERROR"

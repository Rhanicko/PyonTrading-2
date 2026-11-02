from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError

from app.adapters.calendar import FOREX_FACTORY_CALENDAR_PAGE, MANILA_TIME, ForexFactoryCalendarAdapter
from app.schemas.market import CalendarEvent, DataStatus, EventsResponse


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.payload


def test_calendar_filters_usd_events_and_converts_to_manila(monkeypatch):
    payload = b'[{"title":"CPI m/m","country":"USD","date":"2099-01-02T08:30:00-05:00","impact":"High","forecast":"0.2%","previous":"0.1%"},{"title":"Ignored","country":"EUR","date":"2099-01-02T08:30:00-05:00","impact":"High"}]'
    monkeypatch.setattr("app.adapters.calendar.urlopen", lambda *_args, **_kwargs: FakeResponse(payload))

    response = ForexFactoryCalendarAdapter("https://example.test/calendar").upcoming_usd_events()

    assert response.data_status == DataStatus.LIVE
    assert len(response.events) == 1
    assert response.events[0].title == "CPI m/m"
    assert response.events[0].event_time_utc == datetime(2099, 1, 2, 13, 30, tzinfo=UTC)
    assert response.events[0].event_time_manila.hour == 21


def test_calendar_returns_source_error_when_export_is_invalid(monkeypatch):
    monkeypatch.setattr("app.adapters.calendar.urlopen", lambda *_args, **_kwargs: FakeResponse(b'{"unexpected":true}'))

    response = ForexFactoryCalendarAdapter("https://example.test/calendar").upcoming_usd_events()

    assert response.data_status == DataStatus.SOURCE_ERROR
    assert response.reason_codes == ["CALENDAR_FETCH_FAILED", "CALENDAR_INVALID_PAYLOAD"]


def test_calendar_today_scope_keeps_only_remaining_philippine_day_events():
    now = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    today_event = now + timedelta(minutes=30)
    tomorrow_event = now + timedelta(hours=5)
    source = EventsResponse(
        observed_at_utc=now,
        source_timestamp_utc=now,
        data_status=DataStatus.LIVE,
        source_url=FOREX_FACTORY_CALENDAR_PAGE,
        events=[
            CalendarEvent(title="Today", currency="USD", event_time_utc=today_event, event_time_manila=today_event.astimezone(MANILA_TIME), source_url=FOREX_FACTORY_CALENDAR_PAGE),
            CalendarEvent(title="Tomorrow", currency="USD", event_time_utc=tomorrow_event, event_time_manila=tomorrow_event.astimezone(MANILA_TIME), source_url=FOREX_FACTORY_CALENDAR_PAGE),
        ],
    )

    response = ForexFactoryCalendarAdapter._filtered_response(source, now, limit=8, today_only=True)

    assert [event.title for event in response.events] == ["Today"]


def test_calendar_uses_persisted_verified_cache_after_rate_limit(monkeypatch, tmp_path: Path):
    payload = b'[{"title":"CPI m/m","country":"USD","date":"2099-01-02T08:30:00-05:00","impact":"High"}]'
    database = tmp_path / "calendar.db"
    monkeypatch.setattr("app.adapters.calendar.urlopen", lambda *_args, **_kwargs: FakeResponse(payload))
    ForexFactoryCalendarAdapter("https://example.test/calendar", database_path=database).upcoming_usd_events()

    def rate_limited(*_args, **_kwargs):
        raise HTTPError("https://example.test/calendar", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("app.adapters.calendar.urlopen", rate_limited)
    response = ForexFactoryCalendarAdapter("https://example.test/calendar", database_path=database).upcoming_usd_events()

    assert response.data_status == DataStatus.DELAYED
    assert response.reason_codes == ["CALENDAR_REFRESH_FAILED", "CALENDAR_HTTP_429"]
    assert [event.title for event in response.events] == ["CPI m/m"]


def test_calendar_rate_limit_uses_backoff_without_repeating_requests(monkeypatch):
    calls = []

    def rate_limited(*_args, **_kwargs):
        calls.append(True)
        raise HTTPError("https://example.test/calendar", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr("app.adapters.calendar.urlopen", rate_limited)
    adapter = ForexFactoryCalendarAdapter("https://example.test/calendar")

    assert adapter.upcoming_usd_events().data_status == DataStatus.SOURCE_ERROR
    assert adapter.upcoming_usd_events().data_status == DataStatus.SOURCE_ERROR
    assert len(calls) == 1

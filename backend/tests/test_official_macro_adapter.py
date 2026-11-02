from __future__ import annotations

from datetime import UTC, datetime

from app.adapters.official_macro import BLS_ICAL_URL, OfficialMacroScheduleAdapter, parse_bls_ical
from app.schemas.market import DataStatus


def test_bls_ical_parser_retains_utc_release_time():
    events = parse_bls_ical(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Employment Situation\nDTSTART:20990102T133000Z\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    assert events == [("Employment Situation", datetime(2099, 1, 2, 13, 30, tzinfo=UTC))]


def test_official_macro_adapter_labels_schedule_sources_without_forecasts(monkeypatch):
    payloads = {
        BLS_ICAL_URL: b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:Employment Situation\nDTSTART:20990102T133000Z\nEND:VEVENT\nEND:VCALENDAR\n",
        "https://www.bea.gov/news/schedule/": b"<html><title>BEA Release Schedule</title></html>",
        "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm": b"<html><title>FOMC Calendars</title></html>",
    }
    monkeypatch.setattr(OfficialMacroScheduleAdapter, "_fetch_bytes", staticmethod(lambda url: payloads[url]))
    sources = OfficialMacroScheduleAdapter().refresh_if_due()
    assert [source.provider for source in sources] == ["BLS", "BEA", "FEDERAL_RESERVE"]
    assert all(source.data_status == DataStatus.LIVE for source in sources)
    assert sources[0].next_release_title == "Employment Situation"
    assert "FORECAST_ACTUAL_NOT_PROVIDED_BY_THIS_SOURCE" in sources[0].reason_codes

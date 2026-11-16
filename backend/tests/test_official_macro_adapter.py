from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.adapters.official_macro import BLS_ICAL_URL, OfficialMacroScheduleAdapter, parse_bls_ical
from app.schemas.market import DataStatus


def test_schedule_snapshot_does_not_wait_for_network_refresh(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    started, release = Event(), Event()

    def slow_fetch(url):
        started.set()
        release.wait(timeout=5)
        return b"<html><title>Schedule</title></html>"

    monkeypatch.setattr(OfficialMacroScheduleAdapter, "_fetch_bytes", staticmethod(slow_fetch))
    adapter = OfficialMacroScheduleAdapter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        refresh = pool.submit(adapter.refresh_if_due)
        try:
            assert started.wait(timeout=2)
            snapshot = pool.submit(adapter.snapshot).result(timeout=0.5)
            assert len(snapshot) == 3
            assert all("OFFICIAL_SCHEDULE_REFRESH_PENDING" in source.reason_codes for source in snapshot)
        finally:
            release.set()
            refresh.result(timeout=2)


def test_expired_schedule_cache_is_not_reported_live(monkeypatch):
    monkeypatch.setattr(OfficialMacroScheduleAdapter, "_fetch_bytes", staticmethod(lambda url: b"<html><title>Schedule</title></html>"))
    adapter = OfficialMacroScheduleAdapter(ttl_seconds=60)
    adapter.refresh_if_due()
    adapter._fetched_at = datetime.now(UTC) - timedelta(minutes=2)
    snapshot = adapter.snapshot()
    assert all(source.data_status == DataStatus.DELAYED for source in snapshot)
    assert all("OFFICIAL_SCHEDULE_CACHE_EXPIRED" in source.reason_codes for source in snapshot)


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

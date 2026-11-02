from __future__ import annotations

import re
from datetime import UTC, datetime
from html import unescape
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.market import DataStatus, OfficialMacroSource


BLS_ICAL_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule/"
FEDERAL_RESERVE_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"


class OfficialMacroScheduleAdapter:
    """Bounded official release-schedule reader.

    BLS exposes an iCalendar feed. BEA and the Federal Reserve publish human
    release/calendar pages, so their availability is retained even when a
    stable machine-readable next-release timestamp cannot be extracted. This
    adapter does not claim official forecast, previous, or actual values.
    """

    def __init__(self, *, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, OfficialMacroSource] = {}
        self._fetched_at: datetime | None = None
        self._lock = Lock()

    def snapshot(self) -> list[OfficialMacroSource]:
        with self._lock:
            now = datetime.now(UTC)
            if self._fetched_at is None:
                return [self._pending(provider, url, now) for provider, url in _PROVIDERS]
            return [self._cache.get(provider, self._pending(provider, url, now)) for provider, url in _PROVIDERS]

    def refresh_if_due(self) -> list[OfficialMacroSource]:
        with self._lock:
            now = datetime.now(UTC)
            if self._fetched_at and (now - self._fetched_at).total_seconds() < self.ttl_seconds:
                return [self._cache.get(provider, self._pending(provider, url, now)) for provider, url in _PROVIDERS]
            results = {
                "BLS": self._fetch_bls(now),
                "BEA": self._fetch_html_provider("BEA", BEA_SCHEDULE_URL, now),
                "FEDERAL_RESERVE": self._fetch_html_provider("FEDERAL_RESERVE", FEDERAL_RESERVE_FOMC_URL, now),
            }
            self._cache = results
            self._fetched_at = now
            return [results[provider] for provider, _url in _PROVIDERS]

    @staticmethod
    def _pending(provider: str, source_url: str, now: datetime) -> OfficialMacroSource:
        return OfficialMacroSource(
            provider=provider,  # type: ignore[arg-type]
            source_url=source_url,
            data_status=DataStatus.SOURCE_ERROR,
            retrieved_at_utc=now,
            reason_codes=["OFFICIAL_SCHEDULE_REFRESH_PENDING"],
        )

    def _fetch_bls(self, now: datetime) -> OfficialMacroSource:
        try:
            payload = self._fetch_bytes(BLS_ICAL_URL).decode("utf-8", errors="replace")
            releases = parse_bls_ical(payload)
            upcoming = next((item for item in releases if item[1] >= now), None)
            return OfficialMacroSource(
                provider="BLS", source_url=BLS_ICAL_URL, data_status=DataStatus.LIVE,
                retrieved_at_utc=now, source_timestamp_utc=now,
                next_release_title=upcoming[0] if upcoming else None,
                next_release_at_utc=upcoming[1] if upcoming else None,
                reason_codes=["OFFICIAL_SCHEDULE_ONLY", "FORECAST_ACTUAL_NOT_PROVIDED_BY_THIS_SOURCE"],
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            return self._provider_error("BLS", BLS_ICAL_URL, now, error)

    def _fetch_html_provider(self, provider: str, source_url: str, now: datetime) -> OfficialMacroSource:
        try:
            html = self._fetch_bytes(source_url).decode("utf-8", errors="replace")
            if not html.strip():
                raise ValueError("EMPTY_OFFICIAL_SCHEDULE")
            title = extract_html_title(html)
            return OfficialMacroSource(
                provider=provider,  # type: ignore[arg-type]
                source_url=source_url, data_status=DataStatus.LIVE,
                retrieved_at_utc=now, source_timestamp_utc=now,
                next_release_title=title,
                reason_codes=[
                    "OFFICIAL_SCHEDULE_PAGE_AVAILABLE",
                    "NEXT_RELEASE_TIMESTAMP_NOT_MACHINE_VERIFIED",
                    "FORECAST_ACTUAL_NOT_PROVIDED_BY_THIS_SOURCE",
                ],
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            return self._provider_error(provider, source_url, now, error)

    @staticmethod
    def _provider_error(provider: str, source_url: str, now: datetime, error: Exception) -> OfficialMacroSource:
        if isinstance(error, HTTPError):
            reason = f"OFFICIAL_SCHEDULE_HTTP_{error.code}"
        elif isinstance(error, TimeoutError):
            reason = "OFFICIAL_SCHEDULE_TIMEOUT"
        elif isinstance(error, ValueError):
            reason = "OFFICIAL_SCHEDULE_INVALID_PAYLOAD"
        else:
            reason = "OFFICIAL_SCHEDULE_NETWORK_ERROR"
        return OfficialMacroSource(
            provider=provider,  # type: ignore[arg-type]
            source_url=source_url, data_status=DataStatus.SOURCE_ERROR,
            retrieved_at_utc=now, reason_codes=[reason],
        )

    @staticmethod
    def _fetch_bytes(source_url: str) -> bytes:
        request = Request(source_url, headers={"Accept": "text/calendar,text/html", "User-Agent": "PyonTrading2/0.2 official-schedule-reader"})
        with urlopen(request, timeout=5) as response:  # nosec B310 - fixed official provider URLs
            return response.read()


_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("BLS", BLS_ICAL_URL),
    ("BEA", BEA_SCHEDULE_URL),
    ("FEDERAL_RESERVE", FEDERAL_RESERVE_FOMC_URL),
)


def parse_bls_ical(payload: str) -> list[tuple[str, datetime]]:
    """Parse BLS iCalendar VEVENTs with RFC line-folding and US/Eastern times."""
    unfolded = re.sub(r"\r?\n[ \t]", "", payload)
    events: list[tuple[str, datetime]] = []
    for block in re.findall(r"BEGIN:VEVENT\s*(.*?)\s*END:VEVENT", unfolded, flags=re.DOTALL):
        summary_match = re.search(r"^SUMMARY(?:;[^:]*)?:(.+)$", block, flags=re.MULTILINE)
        start_match = re.search(r"^DTSTART(?P<parameters>;[^:]*)?:(?P<value>[^\r\n]+)$", block, flags=re.MULTILINE)
        if not summary_match or not start_match:
            continue
        value = start_match.group("value").strip()
        parameters = start_match.group("parameters") or ""
        try:
            if value.endswith("Z"):
                time = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            else:
                time = datetime.strptime(value, "%Y%m%dT%H%M%S").replace(
                    tzinfo=ZoneInfo("America/New_York") if "TZID" in parameters else UTC
                ).astimezone(UTC)
        except (ValueError, ZoneInfoNotFoundError):
            continue
        events.append((unescape(summary_match.group(1)).strip(), time))
    return sorted(events, key=lambda item: item[1])


def extract_html_title(payload: str) -> str | None:
    title = re.search(r"<title[^>]*>\s*(.*?)\s*</title>", payload, flags=re.IGNORECASE | re.DOTALL)
    if not title:
        return None
    content = re.sub(r"<[^>]+>", "", title.group(1))
    return unescape(re.sub(r"\s+", " ", content)).strip() or None

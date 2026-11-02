from datetime import UTC, datetime, timedelta

from app.schemas.market import Candle, ConnectionResponse, CrossMarketFeature, DataStatus, MarketDepthReport, QuoteResponse
from app.services.source_setup import SourceSetupService
from app.storage.database import store_completed_candles


class SetupAdapter:
    def connection(self, symbol):
        return ConnectionResponse(
            observed_at_utc=datetime.now(UTC), data_status=DataStatus.LIVE,
            terminal_connected=True, configured_symbol=symbol, broker_server="MetaQuotes-Demo",
        )

    def quote(self, symbol):
        now = datetime.now(UTC)
        return QuoteResponse(
            observed_at_utc=now, source_timestamp_utc=now, data_status=DataStatus.LIVE,
            symbol=symbol, bid=4100, ask=4100.2,
        )

    def candles(self, _symbol, _timeframe, _limit):
        now = datetime.now(UTC)
        return DataStatus.LIVE, [], [Candle(
            open_time_utc=now - timedelta(minutes=5), open=4100, high=4101, low=4099,
            close=4100.5, tick_volume=12, completed=True,
        )]

    def market_depth(self, _symbol):
        return MarketDepthReport(
            data_status=DataStatus.LIVE, broker_depth_available=True, level_count=2,
            summary="Broker-only depth is available.",
            reason_codes=["MT5_BROKER_DEPTH_ONLY", "NOT_CONSOLIDATED_FUTURES_DEPTH"],
        )


class SetupCalendar:
    def upcoming_usd_events(self):
        from app.schemas.market import EventsResponse

        now = datetime.now(UTC)
        return EventsResponse(
            observed_at_utc=now, source_timestamp_utc=now, data_status=DataStatus.LIVE,
            source_url="https://example.test/calendar", events=[],
        )


class SetupContext:
    def snapshot(self):
        return [CrossMarketFeature(
            key="DXY", configured_symbol="DXY", data_status=DataStatus.LIVE,
            summary="Context only.", reason_codes=["CONTEXT_ONLY_NOT_CAUSAL"],
        )]


class FailingCalendar:
    def upcoming_usd_events(self):
        raise RuntimeError("calendar unavailable")


class FailingContext:
    def snapshot(self):
        raise RuntimeError("context unavailable")


class FailingDepthAdapter(SetupAdapter):
    def market_depth(self, _symbol):
        raise RuntimeError("depth unavailable")


def test_source_setup_reports_actual_capabilities_without_claiming_futures_flow(tmp_path):
    response = SourceSetupService(SetupAdapter(), SetupCalendar(), tmp_path / "research.db", SetupContext()).snapshot("XAUUSD")

    capabilities = {item.source_id: item for item in response.capabilities}
    assert capabilities["MT5_TERMINAL"].state == "READY"
    assert capabilities["BROKER_TICK_ACTIVITY"].source_category.value == "BROKER_TICK_PROXY"
    assert capabilities["BROKER_DEPTH"].state == "READY"
    assert capabilities["LICENSED_FUTURES_FLOW"].data_status == DataStatus.NOT_CONFIGURED
    assert capabilities["LICENSED_FUTURES_FLOW"].source_category.value == "UNAVAILABLE"
    assert "NO_CREDENTIAL_STORAGE" in response.reason_codes


def test_source_setup_reports_local_archive_coverage_for_the_active_broker_only(tmp_path):
    database = tmp_path / "research.db"
    now = datetime(2026, 10, 23, tzinfo=UTC)
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD", timeframe="M5",
        candles=[Candle(
            open_time_utc=now - timedelta(minutes=10), open=4100, high=4101, low=4099,
            close=4100.5, tick_volume=12, completed=True,
        )], timeframe_seconds=300, observed_at_utc=now,
    )
    store_completed_candles(
        database, source="MT5", broker_server="Another-Broker", symbol="XAUUSD", timeframe="M5",
        candles=[Candle(
            open_time_utc=now - timedelta(minutes=10), open=4200, high=4201, low=4199,
            close=4200.5, tick_volume=12, completed=True,
        )], timeframe_seconds=300, observed_at_utc=now,
    )

    response = SourceSetupService(SetupAdapter(), SetupCalendar(), database).snapshot("XAUUSD")

    assert len(response.archives) == 1
    assert response.archives[0].broker_server == "MetaQuotes-Demo"
    assert response.archives[0].completed_candles == 1
    assert response.archives[0].readiness == "COLLECTING"


def test_source_setup_keeps_capability_response_available_when_optional_sources_fail(tmp_path):
    response = SourceSetupService(
        FailingDepthAdapter(), FailingCalendar(), tmp_path / "research.db", FailingContext(),
    ).snapshot("XAUUSD")

    capabilities = {item.source_id: item for item in response.capabilities}
    assert capabilities["BROKER_DEPTH"].data_status == DataStatus.SOURCE_ERROR
    assert capabilities["USD_CALENDAR"].data_status == DataStatus.SOURCE_ERROR
    assert capabilities["CROSS_MARKET_CONTEXT"].state == "ACTION_REQUIRED"
    assert any(code.startswith("MT5_BROKER_DEPTH_CHECK_FAILED") for code in capabilities["BROKER_DEPTH"].reason_codes)

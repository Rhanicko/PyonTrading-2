from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.adapters.calendar import ForexFactoryCalendarAdapter
from app.adapters.mt5 import MT5Adapter
from app.schemas.market import DataStatus, SourceCapabilitiesResponse, SourceCapability, VolumeSourceCategory
from app.services.cross_market import CrossMarketContextService
from app.storage.database import read_completed_archive_coverage


class SourceSetupService:
    """Test configured research inputs without storing credentials or inventing capability."""

    def __init__(
        self,
        adapter: MT5Adapter,
        calendar: ForexFactoryCalendarAdapter,
        database_path: Path,
        cross_market: CrossMarketContextService | None = None,
    ) -> None:
        self.adapter = adapter
        self.calendar = calendar
        self.database_path = database_path
        self.cross_market = cross_market

    def snapshot(self, symbol: str | None) -> SourceCapabilitiesResponse:
        now = datetime.now(UTC)
        connection = self.adapter.connection(symbol)
        quote = self.adapter.quote(symbol)
        candle_status, candle_reasons, candles = self.adapter.candles(symbol, "M5", 2)
        completed = [bar for bar in candles if bar.completed]
        tick_activity = any(bar.tick_volume > 0 for bar in completed)
        depth_reader = getattr(self.adapter, "market_depth", None)
        depth = None
        depth_error: str | None = None
        if callable(depth_reader):
            try:
                depth = depth_reader(symbol)
            except Exception as error:  # The capability response must remain inspectable on source failure.
                depth_error = f"MT5_BROKER_DEPTH_CHECK_FAILED_{type(error).__name__.upper()}"
        calendar = None
        calendar_error: str | None = None
        try:
            calendar = self.calendar.upcoming_usd_events()
        except Exception as error:
            calendar_error = f"CALENDAR_CAPABILITY_CHECK_FAILED_{type(error).__name__.upper()}"
        context = []
        context_error: str | None = None
        if self.cross_market:
            try:
                context = self.cross_market.snapshot()
            except Exception as error:
                context_error = f"CROSS_MARKET_CAPABILITY_CHECK_FAILED_{type(error).__name__.upper()}"
        ready_context = any(item.data_status == DataStatus.LIVE for item in context)
        archives = read_completed_archive_coverage(
            self.database_path, symbol=symbol, broker_server=connection.broker_server,
        )
        capabilities = [
            SourceCapability(
                source_id="MT5_TERMINAL", label="MT5 terminal", data_status=connection.data_status,
                state="READY" if connection.terminal_connected else "ACTION_REQUIRED",
                provider="LOCAL_META_TRADER_5", summary=(
                    "The local MT5 terminal is connected." if connection.terminal_connected else
                    "Install/open MT5 and sign in outside this application."
                ), setup_hint="Keep the intended terminal open; this application never requests a broker password.",
                reason_codes=connection.reason_codes,
            ),
            SourceCapability(
                source_id="BROKER_CANDLES", label="Broker candles", data_status=candle_status,
                state="READY" if candle_status == DataStatus.LIVE and completed else "ACTION_REQUIRED",
                provider="MT5_BROKER_TERMINAL", summary=(
                    "Completed M5 broker candles are readable." if candle_status == DataStatus.LIVE and completed else
                    "Completed M5 broker candles are unavailable for the selected symbol."
                ), setup_hint="Add the exact broker XAUUSD/GOLD symbol to Market Watch and wait for completed bars.",
                reason_codes=candle_reasons or (["COMPLETED_M5_AVAILABLE"] if completed else ["COMPLETED_M5_UNAVAILABLE"]),
            ),
            SourceCapability(
                source_id="BROKER_TICK_ACTIVITY", label="Broker tick activity", data_status=candle_status,
                state="READY" if candle_status == DataStatus.LIVE and tick_activity else "UNAVAILABLE",
                source_category=VolumeSourceCategory.BROKER_TICK_PROXY, provider="MT5_BROKER_TERMINAL",
                summary=(
                    "MT5 tick activity is available as a participation proxy; it is not consolidated volume."
                    if tick_activity else "No completed broker tick activity is currently available."
                ), setup_hint="Use it only as a broker tick-activity proxy, never as COMEX executed volume.",
                reason_codes=["BROKER_TICK_ACTIVITY_NOT_EXECUTED_VOLUME"] if tick_activity else ["TICK_ACTIVITY_UNAVAILABLE"],
            ),
            SourceCapability(
                source_id="BROKER_DEPTH", label="Broker depth", data_status=depth.data_status if depth else (DataStatus.SOURCE_ERROR if depth_error else DataStatus.NOT_CONFIGURED),
                state="READY" if depth and depth.broker_depth_available else "UNAVAILABLE",
                provider="MT5_BROKER_TERMINAL", summary=depth.summary if depth else "This adapter cannot inspect broker depth.",
                setup_hint="Broker DOM is broker-specific; it does not unlock consolidated futures order flow.",
                reason_codes=depth.reason_codes if depth else [depth_error or "MT5_BROKER_DEPTH_ADAPTER_UNAVAILABLE"],
            ),
            SourceCapability(
                source_id="USD_CALENDAR", label="USD calendar", data_status=calendar.data_status if calendar else DataStatus.SOURCE_ERROR,
                state="READY" if calendar and calendar.data_status == DataStatus.LIVE else "ACTION_REQUIRED",
                provider=calendar.source if calendar else "FOREX_FACTORY_PUBLIC_WEEKLY_EXPORT", summary=(
                    "The configured public calendar is currently reachable." if calendar and calendar.data_status == DataStatus.LIVE else
                    "The public calendar is unavailable or delayed; event risk remains unverified."
                ), setup_hint="Use the source URL and retrieval state shown in the dashboard; public calendar data is informational.",
                reason_codes=calendar.reason_codes if calendar else [calendar_error or "CALENDAR_CAPABILITY_CHECK_FAILED"],
            ),
            SourceCapability(
                source_id="CROSS_MARKET_CONTEXT", label="Cross-market context", data_status=(DataStatus.LIVE if ready_context else DataStatus.NOT_CONFIGURED),
                state="READY" if ready_context else "ACTION_REQUIRED", provider="MT5_CONFIGURED_CONTEXT",
                summary=(
                    "At least one exact broker context symbol is live; it remains contextual, not causal proof."
                    if ready_context else "No configured live DXY, Treasury-yield, oil, or volatility context symbol is available."
                ), setup_hint="Use Context setup with exact broker symbols; they are validated and aliases are not guessed.",
                reason_codes=["CONTEXT_ONLY_NOT_CAUSAL"] if ready_context else [context_error or "CROSS_MARKET_SYMBOL_NOT_CONFIGURED"],
            ),
            SourceCapability(
                source_id="LICENSED_FUTURES_FLOW", label="Licensed futures order flow", data_status=DataStatus.NOT_CONFIGURED,
                state="ACTION_REQUIRED", provider="NO_PROVIDER_CONFIGURED",
                summary="No licensed futures executed-trade/depth provider is configured, so genuine CVD, footprint and futures depth remain unavailable.",
                setup_hint="Choose a licensed provider with historical trades/depth and credentials before adding an audited adapter. Credentials are never entered into this dashboard.",
                reason_codes=["LICENSED_FUTURES_ORDER_FLOW_NOT_CONFIGURED", "NO_SYNTHETIC_ORDER_FLOW"],
            ),
        ]
        return SourceCapabilitiesResponse(
            observed_at_utc=now, source_timestamp_utc=quote.source_timestamp_utc,
            data_status=connection.data_status, symbol=symbol, capabilities=capabilities, archives=archives,
            reason_codes=["CAPABILITY_CHECK_ON_DEMAND", "NO_CREDENTIAL_STORAGE", "NO_ORDER_EXECUTION"],
        )

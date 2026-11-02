from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import os
import subprocess
from typing import Any

from app.config import settings
from app.market.timestamps import MAX_FUTURE_SOURCE_SECONDS, normalize_broker_timestamp
from app.market.timeframes import TIMEFRAME_NAMES
from app.schemas.market import Candle, ConnectionResponse, DataStatus, MarketDepthReport, QuoteResponse, SymbolSummary


GOLD_ALIAS_TERMS = ("XAUUSD", "GOLD")


class MT5Adapter:
    """Thin read-only boundary around the official MT5 terminal package."""

    def __init__(self) -> None:
        self._mt5: Any | None = None
        self._last_error: str | None = None
        self._session_active = False
        try:
            import MetaTrader5 as mt5  # type: ignore[import-not-found]

            self._mt5 = mt5
        except ImportError:
            self._last_error = "MT5_PYTHON_PACKAGE_NOT_INSTALLED"

    def _error(self) -> str:
        if self._mt5 is None:
            return self._last_error or "MT5_PYTHON_PACKAGE_NOT_INSTALLED"
        value = self._mt5.last_error()
        return f"MT5_ERROR_{value[0]}" if value else "MT5_CONNECTION_FAILED"

    def _is_official_mt5_module(self) -> bool:
        """Keep test doubles free from Windows process checks."""
        return getattr(self._mt5, "__name__", None) == "MetaTrader5"

    def _terminal_process_state(self) -> tuple[bool, str | None]:
        """Return whether the configured local terminal is already running."""
        if os.name != "nt":
            return False, "MT5_TERMINAL_PROCESS_CHECK_UNSUPPORTED"
        command = (
            "Get-Process -Name terminal64,terminal -ErrorAction SilentlyContinue "
            "| ForEach-Object { $_.Path }"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                check=False,
                encoding="utf-8",
                errors="replace",
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, "MT5_TERMINAL_PROCESS_CHECK_FAILED"
        running_paths = {
            str(Path(line.strip()).resolve()).casefold()
            for line in result.stdout.splitlines()
            if line.strip()
        }
        if not running_paths:
            if result.returncode != 0:
                return False, "MT5_TERMINAL_PROCESS_CHECK_FAILED"
            return False, "MT5_TERMINAL_NOT_RUNNING"
        if settings.mt5_terminal_path:
            configured_path = str(Path(settings.mt5_terminal_path).resolve()).casefold()
            if configured_path not in running_paths:
                return False, "CONFIGURED_MT5_TERMINAL_NOT_RUNNING"
        return True, None

    def _terminal_executable(self) -> Path | None:
        """Resolve only a configured or conventional local MT5 executable.

        This deliberately does not search recursively or use a broker account
        login.  A configured path wins; the conventional MetaQuotes install
        locations are a convenience for the desktop launcher.
        """
        configured = settings.mt5_terminal_path
        candidates = [Path(configured)] if configured else [
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "MetaTrader 5" / "terminal64.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "MetaTrader 5" / "terminal64.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "MetaTrader 5" / "terminal64.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def start_terminal_at_startup(self) -> tuple[bool, str]:
        """Start MT5 once when PyonTrading starts, without managing it later.

        The terminal itself owns any saved broker login.  This application does
        not receive credentials, perform a login, or relaunch MT5 after the
        user closes it during a running PyonTrading session.
        """
        if not settings.mt5_auto_start:
            return False, "MT5_AUTO_START_DISABLED"
        if not self._is_official_mt5_module():
            return False, "MT5_AUTO_START_UNAVAILABLE"
        running, _ = self._terminal_process_state()
        if running:
            return False, "MT5_TERMINAL_ALREADY_RUNNING"
        executable = self._terminal_executable()
        if executable is None:
            self._last_error = "MT5_TERMINAL_PATH_NOT_FOUND"
            return False, self._last_error
        try:
            subprocess.Popen([str(executable)], close_fds=True)
        except OSError as error:
            self._last_error = f"MT5_TERMINAL_LAUNCH_FAILED_{type(error).__name__.upper()}"
            return False, self._last_error
        self._last_error = "MT5_TERMINAL_LAUNCH_REQUESTED"
        return True, self._last_error

    def _session_is_active(self) -> bool:
        if not self._session_active:
            return False
        terminal_info = getattr(self._mt5, "terminal_info", None)
        if not callable(terminal_info):
            return True
        try:
            return terminal_info() is not None
        except Exception:
            return False

    def shutdown(self) -> None:
        """Release the Python API session without terminating the user's MT5 terminal."""
        self._session_active = False
        shutdown = getattr(self._mt5, "shutdown", None)
        if not callable(shutdown):
            return
        try:
            shutdown()
        except Exception as error:
            self._last_error = f"MT5_SHUTDOWN_FAILED_{type(error).__name__}"

    def connect(self) -> bool:
        if self._mt5 is None:
            return False
        if self._session_is_active():
            return True
        if self._session_active:
            self.shutdown()
        if self._is_official_mt5_module():
            terminal_running, reason = self._terminal_process_state()
            if not terminal_running:
                self._last_error = reason or "MT5_TERMINAL_NOT_RUNNING"
                return False
        kwargs: dict[str, str] = {}
        if settings.mt5_terminal_path:
            kwargs["path"] = settings.mt5_terminal_path
        connected = bool(self._mt5.initialize(**kwargs))
        self._session_active = connected
        if not connected:
            self._last_error = self._error()
        return connected

    def connection(self, configured_symbol: str | None) -> ConnectionResponse:
        observed = datetime.now(UTC)
        if not self.connect():
            return ConnectionResponse(
                observed_at_utc=observed,
                data_status=DataStatus.DISCONNECTED,
                terminal_connected=False,
                terminal_path=settings.mt5_terminal_path,
                configured_symbol=configured_symbol,
                reason_codes=[self._last_error or "MT5_TERMINAL_NOT_AVAILABLE"],
            )
        terminal = self._mt5.terminal_info()
        account = self._mt5.account_info()
        raw_symbols = self._mt5.symbols_get() or []
        gold_symbols = [
            SymbolSummary(name=item.name, visible=bool(item.visible))
            for item in raw_symbols
            if any(term in item.name.upper() for term in GOLD_ALIAS_TERMS)
        ]
        mode_value = getattr(account, "trade_mode", None)
        demo = getattr(self._mt5, "ACCOUNT_TRADE_MODE_DEMO", object())
        real = getattr(self._mt5, "ACCOUNT_TRADE_MODE_REAL", object())
        mode = "DEMO" if mode_value == demo else "LIVE" if mode_value == real else "UNKNOWN"
        return ConnectionResponse(
            observed_at_utc=observed,
            data_status=DataStatus.LIVE,
            terminal_connected=bool(terminal),
            terminal_path=getattr(terminal, "path", settings.mt5_terminal_path),
            broker_server=getattr(account, "server", None),
            account_mode=mode,
            configured_symbol=configured_symbol,
            gold_symbols=gold_symbols,
        )

    def quote(self, symbol: str | None) -> QuoteResponse:
        observed = datetime.now(UTC)
        if not symbol:
            return QuoteResponse(observed_at_utc=observed, data_status=DataStatus.NOT_CONFIGURED, reason_codes=["SYMBOL_NOT_SELECTED"])
        if not self.connect():
            return QuoteResponse(symbol=symbol, observed_at_utc=observed, data_status=DataStatus.DISCONNECTED, reason_codes=[self._last_error or "MT5_TERMINAL_NOT_AVAILABLE"])
        info = self._mt5.symbol_info(symbol)
        tick = self._mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            return QuoteResponse(symbol=symbol, observed_at_utc=observed, data_status=DataStatus.SOURCE_ERROR, reason_codes=["SYMBOL_OR_TICK_UNAVAILABLE", self._error()])
        raw_source_time = datetime.fromtimestamp(tick.time, UTC)
        timestamp = normalize_broker_timestamp(raw_source_time, observed_at_utc=observed)
        source_time = timestamp.effective_utc
        from app.market.freshness import data_status_for_tick, is_weekend_utc

        status, age = data_status_for_tick(
            source_time,
            now=observed,
            delayed_seconds=settings.delayed_seconds,
            stale_seconds=settings.stale_seconds,
        )
        point = float(info.point)
        bid, ask = float(tick.bid), float(tick.ask)
        reasons: list[str] = []
        invalid_quote = not ask >= bid > 0
        if invalid_quote:
            reasons.append("INVALID_OR_CROSSED_QUOTE")
        if timestamp.normalized:
            reasons.append(f"BROKER_CLOCK_OFFSET_NORMALIZED_{timestamp.broker_clock_offset_seconds}S")
        if status == DataStatus.SOURCE_ERROR and age is not None and age < 0:
            reasons.append("FUTURE_BROKER_TIMESTAMP")
        if status == DataStatus.STALE and is_weekend_utc(observed):
            status = DataStatus.MARKET_CLOSED
            reasons.append("WEEKEND_OR_MARKET_CLOSED")
        if invalid_quote:
            status = DataStatus.SOURCE_ERROR
        if status == DataStatus.SOURCE_ERROR:
            return QuoteResponse(
                symbol=symbol,
                observed_at_utc=observed,
                source_timestamp_utc=source_time,
                raw_source_timestamp_utc=raw_source_time,
                broker_clock_offset_seconds=timestamp.broker_clock_offset_seconds,
                timestamp_normalized=timestamp.normalized,
                data_status=status,
                reason_codes=reasons or ["BROKER_QUOTE_UNVERIFIED"],
                tick_age_seconds=age,
            )
        return QuoteResponse(
            symbol=symbol, observed_at_utc=observed, source_timestamp_utc=source_time,
            raw_source_timestamp_utc=raw_source_time,
            broker_clock_offset_seconds=timestamp.broker_clock_offset_seconds,
            timestamp_normalized=timestamp.normalized,
            data_status=status, reason_codes=reasons, bid=bid, ask=ask,
            spread_price=ask - bid, spread_points=(ask - bid) / point if point else None,
            tick_age_seconds=age, digits=int(info.digits), point=point,
            tick_size=float(info.trade_tick_size), tick_value=float(info.trade_tick_value),
            volume_min=float(info.volume_min), volume_max=float(info.volume_max), volume_step=float(info.volume_step),
            contract_size=float(info.trade_contract_size), stops_level_points=int(info.trade_stops_level),
            freeze_level_points=int(info.trade_freeze_level),
        )

    def candles(self, symbol: str | None, timeframe: str, limit: int) -> tuple[DataStatus, list[str], list[Candle]]:
        observed = datetime.now(UTC)
        if not symbol:
            return DataStatus.NOT_CONFIGURED, ["SYMBOL_NOT_SELECTED"], []
        if timeframe not in TIMEFRAME_NAMES:
            return DataStatus.SOURCE_ERROR, ["UNSUPPORTED_TIMEFRAME"], []
        if not self.connect():
            return DataStatus.DISCONNECTED, [self._last_error or "MT5_TERMINAL_NOT_AVAILABLE"], []
        mt5_timeframe = getattr(self._mt5, f"TIMEFRAME_{timeframe}")
        # MT5 start position 0 is the current forming bar. The latest returned bar is marked incomplete.
        rates = self._mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, limit)
        if rates is None or len(rates) < 2:
            return DataStatus.HISTORY_INSUFFICIENT, ["BROKER_HISTORY_INSUFFICIENT", self._error()], []
        raw_latest_open_time = datetime.fromtimestamp(int(rates[-1]["time"]), UTC)
        tick_lookup = getattr(self._mt5, "symbol_info_tick", None)
        raw_tick = tick_lookup(symbol) if callable(tick_lookup) else None
        timestamp = normalize_broker_timestamp(
            datetime.fromtimestamp(raw_tick.time, UTC) if raw_tick is not None else raw_latest_open_time,
            observed_at_utc=observed,
        )
        candles = []
        for index, row in enumerate(rates):
            raw_open_time = datetime.fromtimestamp(int(row["time"]), UTC)
            candles.append(Candle(
                open_time_utc=raw_open_time - timedelta(seconds=timestamp.broker_clock_offset_seconds),
                open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
                tick_volume=int(row["tick_volume"]), real_volume=int(row["real_volume"]) if "real_volume" in row.dtype.names else None,
                spread_points=int(row["spread"]) if "spread" in row.dtype.names else None,
                completed=index != len(rates) - 1,
                raw_open_time_utc=raw_open_time,
                broker_clock_offset_seconds=timestamp.broker_clock_offset_seconds,
                timestamp_normalized=timestamp.normalized,
            ))
        latest_open_time = candles[-1].open_time_utc
        if latest_open_time > observed + timedelta(seconds=MAX_FUTURE_SOURCE_SECONDS):
            return DataStatus.SOURCE_ERROR, ["FUTURE_BROKER_CANDLE_TIMESTAMP"], []
        reasons = [f"BROKER_CLOCK_OFFSET_NORMALIZED_{timestamp.broker_clock_offset_seconds}S"] if timestamp.normalized else []
        return DataStatus.LIVE, reasons, candles

    def market_depth(self, symbol: str | None) -> MarketDepthReport:
        """Return broker DOM capability without mislabelling it as futures flow.

        MetaTrader's book API is a broker-symbol-specific displayed book.  The
        adapter subscribes only long enough to capture a bounded capability
        snapshot and immediately releases it; no high-frequency depth stream is
        sent to the dashboard or stored as a COMEX order book.
        """
        if not symbol:
            return MarketDepthReport(
                data_status=DataStatus.NOT_CONFIGURED,
                summary="Select an exact broker symbol before depth capability can be checked.",
                reason_codes=["SYMBOL_NOT_SELECTED", "MT5_BROKER_DEPTH_UNAVAILABLE"],
            )
        if not self.connect():
            return MarketDepthReport(
                data_status=DataStatus.DISCONNECTED,
                summary="MT5 is disconnected; broker depth capability cannot be checked.",
                reason_codes=[self._last_error or "MT5_TERMINAL_NOT_AVAILABLE"],
            )
        info = self._mt5.symbol_info(symbol)
        if info is None:
            return MarketDepthReport(
                data_status=DataStatus.SOURCE_ERROR,
                summary="The selected broker symbol has no readable contract metadata.",
                reason_codes=["SYMBOL_INFO_UNAVAILABLE", self._error()],
            )
        declared_depth = int(getattr(info, "ticks_bookdepth", 0) or 0)
        add = getattr(self._mt5, "market_book_add", None)
        get = getattr(self._mt5, "market_book_get", None)
        release = getattr(self._mt5, "market_book_release", None)
        if declared_depth <= 0 or not callable(add) or not callable(get):
            return MarketDepthReport(
                data_status=DataStatus.NOT_CONFIGURED,
                summary="This MT5 broker/symbol does not expose a readable market-depth book.",
                reason_codes=["MT5_BROKER_DEPTH_NOT_AVAILABLE", "NOT_CONSOLIDATED_FUTURES_DEPTH"],
            )
        subscribed = bool(add(symbol))
        try:
            levels = get(symbol) if subscribed else None
        finally:
            if subscribed and callable(release):
                release(symbol)
        if not levels:
            return MarketDepthReport(
                data_status=DataStatus.NOT_CONFIGURED,
                summary="MT5 reports depth support but did not return a current broker book snapshot.",
                reason_codes=["MT5_BROKER_DEPTH_EMPTY", "NOT_CONSOLIDATED_FUTURES_DEPTH"],
            )
        return MarketDepthReport(
            data_status=DataStatus.LIVE, broker_depth_available=True, level_count=len(levels),
            summary="A broker-specific displayed depth snapshot is available; it is not presented as COMEX futures depth.",
            reason_codes=["MT5_BROKER_DEPTH_ONLY", "DISPLAYED_ORDERS_CAN_CANCEL", "NOT_CONSOLIDATED_FUTURES_DEPTH"],
        )

    def enable_context_symbol(self, symbol: str) -> tuple[bool, list[str]]:
        """Make one exact existing MT5 instrument visible for read-only context collection."""
        if not self.connect():
            return False, [self._last_error or "MT5_TERMINAL_NOT_AVAILABLE"]
        info = self._mt5.symbol_info(symbol)
        if info is None:
            return False, ["CONTEXT_SYMBOL_NOT_DISCOVERED"]
        if bool(getattr(info, "visible", False)):
            return True, ["CONTEXT_SYMBOL_ALREADY_VISIBLE"]
        selector = getattr(self._mt5, "symbol_select", None)
        if not callable(selector) or not bool(selector(symbol, True)):
            return False, ["CONTEXT_SYMBOL_MARKET_WATCH_ENABLE_FAILED", self._error()]
        return True, ["CONTEXT_SYMBOL_ENABLED_IN_MARKET_WATCH"]


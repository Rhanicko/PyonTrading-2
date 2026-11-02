from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import numpy as np

from app.adapters.mt5 import MT5Adapter
from app.schemas.market import DataStatus


class FakeMT5:
    TIMEFRAME_M5 = 5

    def initialize(self, **kwargs):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start, limit):
        return np.array([
            (1761033600, 2700.12345, 2702.12345, 2699.12345, 2701.12345, 10, 3, 0),
            (1761033900, 2701.12345, 2703.12345, 2700.12345, 2702.98765, 12, 4, 0),
        ], dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8"), ("spread", "i8"), ("real_volume", "i8")])

    def last_error(self):
        return (0, "OK")


class FutureCandleMT5(FakeMT5):
    def copy_rates_from_pos(self, symbol, timeframe, start, limit):
        future = int((datetime.now(UTC) + timedelta(minutes=3)).timestamp())
        return np.array([
            (future - 300, 2700.0, 2702.0, 2699.0, 2701.0, 10, 3, 0),
            (future, 2701.0, 2703.0, 2700.0, 2702.0, 12, 4, 0),
        ], dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8"), ("spread", "i8"), ("real_volume", "i8")])


class OffsetClockMT5(FakeMT5):
    def symbol_info(self, _symbol):
        return SimpleNamespace(
            point=0.01,
            digits=2,
            trade_tick_size=0.01,
            trade_tick_value=0.1,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_contract_size=100.0,
            trade_stops_level=0,
            trade_freeze_level=0,
        )

    def symbol_info_tick(self, _symbol):
        return SimpleNamespace(
            time=int((datetime.now(UTC) + timedelta(hours=3)).timestamp()),
            bid=2700.0,
            ask=2700.2,
        )

    def copy_rates_from_pos(self, symbol, timeframe, start, limit):
        future = int((datetime.now(UTC) + timedelta(hours=3)).timestamp())
        return np.array([
            (future - 300, 2700.0, 2702.0, 2699.0, 2701.0, 10, 3, 0),
            (future, 2701.0, 2703.0, 2700.0, 2702.0, 12, 4, 0),
        ], dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8"), ("tick_volume", "i8"), ("spread", "i8"), ("real_volume", "i8")])


class DepthMT5(FakeMT5):
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.released: list[str] = []

    def symbol_info(self, _symbol):
        return SimpleNamespace(ticks_bookdepth=4)

    def market_book_add(self, symbol):
        self.subscribed.append(symbol)
        return True

    def market_book_get(self, _symbol):
        return (SimpleNamespace(type=1, price=4100.0, volume=2), SimpleNamespace(type=2, price=4100.1, volume=3))

    def market_book_release(self, symbol):
        self.released.append(symbol)
        return True


class ContextSymbolMT5(FakeMT5):
    def __init__(self, info):
        self.info = info
        self.selected: list[tuple[str, bool]] = []

    def symbol_info(self, _symbol):
        return self.info

    def symbol_select(self, symbol, visible):
        self.selected.append((symbol, visible))
        return True


class LifecycleMT5(FakeMT5):
    def __init__(self, terminal_available: bool = True) -> None:
        self.__name__ = "MetaTrader5"
        self.terminal_available = terminal_available
        self.initialize_calls = 0
        self.shutdown_calls = 0

    def initialize(self, **kwargs):
        self.initialize_calls += 1
        return True

    def terminal_info(self):
        return SimpleNamespace() if self.terminal_available else None

    def shutdown(self):
        self.shutdown_calls += 1


def test_latest_mt5_bar_is_marked_forming_and_values_keep_precision():
    adapter = MT5Adapter()
    adapter._mt5 = FakeMT5()
    status, reasons, candles = adapter.candles("XAUUSD", "M5", 2)
    assert status == DataStatus.LIVE
    assert reasons == []
    assert candles[0].completed is True
    assert candles[1].completed is False
    assert candles[1].close == 2702.98765
    assert candles[0].open_time_utc == datetime.fromtimestamp(1761033600, UTC)


def test_missing_symbol_never_returns_a_substitute_quote():
    adapter = MT5Adapter()
    result = adapter.quote(None)
    assert result.data_status == DataStatus.NOT_CONFIGURED
    assert result.bid is None and result.ask is None


def test_future_broker_candle_timestamp_is_not_returned_as_live_history():
    adapter = MT5Adapter()
    adapter._mt5 = FutureCandleMT5()

    status, reasons, candles = adapter.candles("XAUUSD", "M5", 2)

    assert status == DataStatus.SOURCE_ERROR
    assert reasons == ["FUTURE_BROKER_CANDLE_TIMESTAMP"]
    assert candles == []


def test_whole_hour_broker_clock_offset_is_normalized_and_keeps_raw_timestamp():
    adapter = MT5Adapter()
    adapter._mt5 = OffsetClockMT5()

    quote = adapter.quote("XAUUSD")
    status, reasons, candles = adapter.candles("XAUUSD", "M5", 2)

    assert quote.data_status == DataStatus.LIVE
    assert quote.timestamp_normalized is True
    assert quote.broker_clock_offset_seconds == 10_800
    assert "BROKER_CLOCK_OFFSET_NORMALIZED_10800S" in quote.reason_codes
    assert quote.raw_source_timestamp_utc is not None
    assert status == DataStatus.LIVE
    assert reasons == ["BROKER_CLOCK_OFFSET_NORMALIZED_10800S"]
    assert candles[-1].timestamp_normalized is True
    assert candles[-1].raw_open_time_utc is not None


def test_broker_depth_snapshot_is_released_and_not_relabelled_as_futures_depth():
    adapter = MT5Adapter()
    fake = DepthMT5()
    adapter._mt5 = fake

    depth = adapter.market_depth("XAUUSD")

    assert depth.data_status == DataStatus.LIVE
    assert depth.broker_depth_available is True
    assert depth.level_count == 2
    assert depth.source_category.value == "UNAVAILABLE"
    assert "NOT_CONSOLIDATED_FUTURES_DEPTH" in depth.reason_codes
    assert fake.subscribed == ["XAUUSD"]
    assert fake.released == ["XAUUSD"]


def test_context_symbol_must_exist_and_is_made_visible_only_after_validation():
    adapter = MT5Adapter()
    fake = ContextSymbolMT5(SimpleNamespace(visible=False))
    adapter._mt5 = fake

    enabled, reasons = adapter.enable_context_symbol("DXY.broker")

    assert enabled is True
    assert reasons == ["CONTEXT_SYMBOL_ENABLED_IN_MARKET_WATCH"]
    assert fake.selected == [("DXY.broker", True)]


def test_unknown_context_symbol_is_not_enabled_or_substituted():
    adapter = MT5Adapter()
    fake = ContextSymbolMT5(None)
    adapter._mt5 = fake

    enabled, reasons = adapter.enable_context_symbol("DXY")

    assert enabled is False
    assert reasons == ["CONTEXT_SYMBOL_NOT_DISCOVERED"]
    assert fake.selected == []


def test_closed_mt5_terminal_is_not_relaunched_by_the_adapter():
    adapter = MT5Adapter()
    fake = LifecycleMT5(terminal_available=False)
    adapter._mt5 = fake
    adapter._session_active = True
    adapter._terminal_process_state = lambda: (False, "MT5_TERMINAL_NOT_RUNNING")

    assert adapter.connect() is False
    assert fake.shutdown_calls == 1
    assert fake.initialize_calls == 0
    assert adapter._last_error == "MT5_TERMINAL_NOT_RUNNING"


def test_startup_launches_a_discovered_terminal_once(monkeypatch):
    adapter = MT5Adapter()
    adapter._mt5 = LifecycleMT5()
    executable = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
    launches: list[tuple[list[str], dict]] = []
    adapter._terminal_process_state = lambda: (False, "MT5_TERMINAL_NOT_RUNNING")
    adapter._terminal_executable = lambda: __import__("pathlib").Path(executable)
    monkeypatch.setattr(
        "app.adapters.mt5.subprocess.Popen",
        lambda command, **kwargs: launches.append((command, kwargs)),
    )

    started, status = adapter.start_terminal_at_startup()

    assert started is True
    assert status == "MT5_TERMINAL_LAUNCH_REQUESTED"
    assert launches == [([executable], {"close_fds": True})]


def test_startup_does_not_duplicate_a_running_terminal():
    adapter = MT5Adapter()
    adapter._mt5 = LifecycleMT5()
    adapter._terminal_process_state = lambda: (True, None)

    started, status = adapter.start_terminal_at_startup()

    assert started is False
    assert status == "MT5_TERMINAL_ALREADY_RUNNING"


def test_adapter_connects_only_after_mt5_is_already_running():
    adapter = MT5Adapter()
    fake = LifecycleMT5()
    adapter._mt5 = fake
    adapter._terminal_process_state = lambda: (True, None)

    assert adapter.connect() is True
    assert fake.initialize_calls == 1


def test_process_check_accepts_a_running_terminal_when_an_optional_name_is_absent(monkeypatch):
    adapter = MT5Adapter()
    monkeypatch.setattr(
        "app.adapters.mt5.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="C:\\Program Files\\MetaTrader 5\\terminal64.exe\n",
        ),
    )

    running, reason = adapter._terminal_process_state()

    assert running is True
    assert reason is None


import asyncio
from datetime import UTC, datetime, timedelta

from app.schemas.market import Candle, DataStatus, QuoteResponse
from app.services.live import LiveService


class FakeSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)

    async def accept(self):
        pass


class FakeAdapter:
    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)
        self.shutdown_calls = 0

    def candles(self, symbol, timeframe, limit):
        return DataStatus.LIVE, [], next(self.snapshots)

    def shutdown(self):
        self.shutdown_calls += 1


def candle(at: datetime, close: float) -> Candle:
    return Candle(open_time_utc=at, open=close - 1, high=close + 1, low=close - 2, close=close, tick_volume=10, completed=False)


def test_m5_stream_emits_update_then_closed_transition():
    start = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    adapter = FakeAdapter([[candle(start - timedelta(minutes=5), 4100), candle(start, 4101)], [candle(start, 4103), candle(start + timedelta(minutes=5), 4104)]])
    service = LiveService(adapter, "XAUUSD")
    socket = FakeSocket()
    service.clients.add(socket)
    closed = []
    service.on_completed_bar = lambda symbol, bar: closed.append((symbol, bar))

    asyncio.run(service._publish_m5_bar_state())
    asyncio.run(service._publish_m5_bar_state())

    assert [event["type"] for event in socket.events] == ["bar_update", "bar_closed", "bar_update"]
    assert socket.events[1]["payload"]["candle"]["completed"] is True
    assert socket.events[1]["payload"]["candle"]["close"] == 4103
    assert socket.events[-1]["payload"]["candle"]["close"] == 4104
    assert [(symbol, bar.close) for symbol, bar in closed] == [("XAUUSD", 4103)]


def test_slow_terminal_read_yields_to_other_async_work():
    import threading

    release = threading.Event()

    class SlowAdapter(FakeAdapter):
        def quote(self, symbol):
            release.wait(timeout=0.2)
            return QuoteResponse(observed_at_utc=datetime.now(UTC), data_status=DataStatus.DISCONNECTED)

    async def exercise():
        service = LiveService(SlowAdapter([]), "XAUUSD")
        task = asyncio.create_task(service._poll())
        try:
            await asyncio.sleep(0)
            assert service.latest_quote is None, "Synchronous terminal access blocked the event loop"
        finally:
            release.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(exercise())


def test_stopping_live_service_releases_the_mt5_api_session():
    adapter = FakeAdapter([])
    service = LiveService(adapter, "XAUUSD")

    asyncio.run(service.stop())

    assert adapter.shutdown_calls == 1


def test_websocket_open_does_not_claim_a_live_broker_before_a_quote_arrives():
    service = LiveService(FakeAdapter([]), "XAUUSD")
    socket = FakeSocket()

    asyncio.run(service.register(socket))

    assert socket.events[0]["payload"]["data_status"] == "CONNECTING"
    assert socket.events[0]["payload"]["reason_codes"] == ["QUOTE_NOT_YET_OBSERVED"]


def test_websocket_open_reports_the_last_observed_broker_state():
    service = LiveService(FakeAdapter([]), "XAUUSD")
    service.latest_quote = QuoteResponse(
        observed_at_utc=datetime.now(UTC), data_status=DataStatus.MARKET_CLOSED,
        reason_codes=["BROKER_SESSION_CLOSED"],
    )
    socket = FakeSocket()

    asyncio.run(service.register(socket))

    assert socket.events[0]["payload"]["data_status"] == "MARKET_CLOSED"
    assert socket.events[0]["payload"]["reason_codes"] == ["BROKER_SESSION_CLOSED"]


def test_symbol_change_discards_an_inflight_candle_window():
    import threading

    entered, release = threading.Event(), threading.Event()
    start = datetime(2026, 11, 16, tzinfo=UTC)

    class SlowAdapter(FakeAdapter):
        def candles(self, symbol, timeframe, limit):
            entered.set()
            release.wait(timeout=2)
            return DataStatus.LIVE, [], [candle(start, 4100)]

    async def exercise():
        service = LiveService(SlowAdapter([]), "XAUUSD")
        socket = FakeSocket()
        service.clients.add(socket)
        task = asyncio.create_task(service._publish_m5_bar_state())
        await asyncio.to_thread(entered.wait, 1)
        service.set_configured_symbol("XAUUSD.a")
        release.set()
        await task
        assert socket.events == [], "Old-symbol OHLC was broadcast under the new symbol"
        assert service._forming_m5 is None

    asyncio.run(exercise())


def test_symbol_change_clears_cached_quote_before_websocket_registration():
    service = LiveService(FakeAdapter([]), "XAUUSD")
    service.latest_quote = QuoteResponse(
        symbol="XAUUSD", observed_at_utc=datetime.now(UTC), data_status=DataStatus.LIVE,
    )
    service.set_configured_symbol("XAUUSD.a")
    socket = FakeSocket()
    asyncio.run(service.register(socket))
    assert service.latest_quote is None
    assert socket.events[0]["payload"]["data_status"] == "CONNECTING"


def test_symbol_change_discards_an_inflight_quote():
    import threading

    entered, release = threading.Event(), threading.Event()

    class SlowAdapter(FakeAdapter):
        def quote(self, symbol):
            entered.set()
            release.wait(timeout=2)
            return QuoteResponse(symbol=symbol, observed_at_utc=datetime.now(UTC), data_status=DataStatus.LIVE)

    async def exercise():
        service = LiveService(SlowAdapter([]), "XAUUSD")
        socket = FakeSocket()
        service.clients.add(socket)
        task = asyncio.create_task(service._poll())
        try:
            await asyncio.to_thread(entered.wait, 1)
            service.set_configured_symbol("XAUUSD.a")
            release.set()
            # Wait for the in-flight read to finish, rather than cancel it first.
            for _ in range(20):
                await asyncio.sleep(0.005)
            assert not any(event["payload"].get("symbol") == "XAUUSD" for event in socket.events)
            assert service.latest_quote is None
        finally:
            release.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(exercise())

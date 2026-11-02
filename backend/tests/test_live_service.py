import asyncio
from datetime import UTC, datetime, timedelta

from app.schemas.market import Candle, DataStatus
from app.services.live import LiveService


class FakeSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


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

    asyncio.run(service._publish_m5_bar_state())
    asyncio.run(service._publish_m5_bar_state())

    assert [event["type"] for event in socket.events] == ["bar_update", "bar_closed", "bar_update"]
    assert socket.events[1]["payload"]["candle"]["completed"] is True
    assert socket.events[-1]["payload"]["candle"]["close"] == 4104


def test_stopping_live_service_releases_the_mt5_api_session():
    adapter = FakeAdapter([])
    service = LiveService(adapter, "XAUUSD")

    asyncio.run(service.stop())

    assert adapter.shutdown_calls == 1

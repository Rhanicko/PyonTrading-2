from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas.market import Candle, DataStatus, QuoteResponse
from app.services.backtest import BacktestCoordinator
from app.storage.database import read_recent_backtest_runs


class FakeAdapter:
    def __init__(self, candles: list[Candle], point: float | None = 0.01) -> None:
        self.values = candles
        self.point = point

    def candles(self, _symbol, _timeframe, _limit):
        return DataStatus.LIVE, [], self.values

    def quote(self, symbol):
        now = datetime.now(UTC)
        return QuoteResponse(
            observed_at_utc=now, source_timestamp_utc=now, data_status=DataStatus.LIVE,
            symbol=symbol, bid=4000, ask=4000.03, point=self.point,
        )


class ArchiveAdapter(FakeAdapter):
    def connection(self, symbol):
        from app.schemas.market import ConnectionResponse

        return ConnectionResponse(
            observed_at_utc=datetime.now(UTC), data_status=DataStatus.LIVE,
            terminal_connected=True, configured_symbol=symbol, broker_server="MetaQuotes-Demo",
        )


def source_candles() -> list[Candle]:
    start = datetime(2026, 10, 1, tzinfo=UTC)
    return [
        Candle(
            open_time_utc=start + timedelta(minutes=index * 5), open=4000 + index,
            high=4001.2 + index, low=3999.4 + index, close=4000.8 + index,
            tick_volume=10, spread_points=3, completed=True,
        )
        for index in range(180)
    ]


def test_coordinator_records_an_immutable_broker_candle_research_run(tmp_path: Path):
    response = BacktestCoordinator(FakeAdapter(source_candles()), tmp_path / "research.db").run("XAUUSD")

    assert response.run_id is not None
    assert response.completed_candles == 180
    assert len(response.results) == 9
    assert "COMMISSION_UNAVAILABLE" in response.reason_codes
    records = read_recent_backtest_runs(tmp_path / "research.db")
    assert records[0]["run_id"] == response.run_id
    assert records[0]["completed_candles"] == 180


def test_coordinator_marks_costs_unavailable_without_broker_point(tmp_path: Path):
    response = BacktestCoordinator(FakeAdapter(source_candles(), point=None), tmp_path / "research.db").run("XAUUSD")

    assert "POINT_VALUE_UNAVAILABLE" in response.reason_codes
    assert all(item.net_points is None for item in response.results)


def test_coordinator_prefers_active_broker_archive_over_a_fresh_adapter_window(tmp_path: Path):
    from app.storage.database import store_completed_candles

    database = tmp_path / "research.db"
    archived = source_candles()
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD", timeframe="M5",
        candles=archived, timeframe_seconds=300, observed_at_utc=datetime.now(UTC),
    )
    response = BacktestCoordinator(ArchiveAdapter(source_candles()[:90]), database).run("XAUUSD")

    assert response.completed_candles == len(archived)
    assert "LOCAL_ARCHIVE_ACTIVE_BROKER_ONLY" in response.reason_codes
    assert "BACKTEST_CURRENT_MT5_HISTORY_FALLBACK" not in response.reason_codes

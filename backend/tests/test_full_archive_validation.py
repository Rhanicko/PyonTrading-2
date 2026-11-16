from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.schemas.market import Candle, DataStatus, QuoteResponse
from app.services.backtest import BacktestCoordinator
from app.storage.database import store_completed_candles


def _adapter(server: str):
    quote = QuoteResponse(
        observed_at_utc=datetime(2026, 11, 14, tzinfo=UTC), data_status=DataStatus.MARKET_CLOSED,
        symbol="XAUUSD", point=0.01,
    )
    return SimpleNamespace(
        quote=lambda symbol: quote,
        connection=lambda symbol: SimpleNamespace(data_status=DataStatus.LIVE, broker_server=server),
    )


def test_walk_forward_uses_full_same_broker_archive_even_while_market_is_closed(tmp_path):
    database = tmp_path / "research.db"
    start = datetime(2026, 10, 1, tzinfo=UTC)
    candles = [Candle(
        open_time_utc=start + timedelta(minutes=5 * index),
        open=4000 + index * 0.03, high=4001 + index * 0.03,
        low=3999 + index * 0.03, close=4000.5 + index * 0.03,
        tick_volume=10, spread_points=3, completed=True,
    ) for index in range(6_001)]
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD",
        timeframe="M5", candles=candles, timeframe_seconds=300, observed_at_utc=start,
    )

    result = BacktestCoordinator(_adapter("MetaQuotes-Demo"), database).validate_archive("XAUUSD")

    assert result.completed_candles == 6_001
    assert result.data_status == DataStatus.MARKET_CLOSED
    assert result.broker_server == "MetaQuotes-Demo"
    assert len(result.results) == 9
    assert all(item.state in {"REVIEW_REQUIRED", "INSUFFICIENT_DATA"} for item in result.results)
    assert "NO_MODEL_PROMOTION" in result.reason_codes
    assert "COMMISSION_UNAVAILABLE" in result.reason_codes


def test_walk_forward_does_not_borrow_another_brokers_archive(tmp_path):
    database = tmp_path / "research.db"
    start = datetime(2026, 10, 1, tzinfo=UTC)
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD",
        timeframe="M5", candles=[Candle(
            open_time_utc=start, open=4000, high=4001, low=3999, close=4000.5,
            tick_volume=10, spread_points=3, completed=True,
        )], timeframe_seconds=300, observed_at_utc=start,
    )

    result = BacktestCoordinator(_adapter("HFM-Demo"), database).validate_archive("XAUUSD")

    assert result.completed_candles == 0
    assert result.results == []
    assert "NO_ACTIVE_BROKER_ARCHIVE" in result.reason_codes


def test_walk_forward_route_returns_an_explicit_unavailable_state(tmp_path):
    app = FastAPI()
    app.include_router(routes.router)
    app.state.live_service = SimpleNamespace(configured_symbol="XAUUSD")
    app.state.backtest_service = BacktestCoordinator(_adapter("HFM-Demo"), tmp_path / "empty.db")

    with TestClient(app) as client:
        response = client.post("/api/backtests/validate")

    assert response.status_code == 200
    assert response.json()["completed_candles"] == 0
    assert response.json()["results"] == []
    assert "NO_ACTIVE_BROKER_ARCHIVE" in response.json()["reason_codes"]


def test_walk_forward_reuses_unchanged_broker_archive_and_invalidates_on_new_bar(tmp_path):
    database = tmp_path / "research.db"
    start = datetime(2026, 10, 1, tzinfo=UTC)
    first = Candle(
        open_time_utc=start, open=4000, high=4001, low=3999, close=4000.5,
        tick_volume=10, spread_points=3, completed=True,
    )
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD",
        timeframe="M5", candles=[first], timeframe_seconds=300, observed_at_utc=start,
    )
    coordinator = BacktestCoordinator(_adapter("MetaQuotes-Demo"), database)

    initial = coordinator.validate_archive("XAUUSD")
    repeated = coordinator.validate_archive("XAUUSD")

    assert initial.cache_hit is False
    assert repeated.cache_hit is True
    assert repeated.completed_candles == 1
    assert repeated.dataset_end_utc == initial.dataset_end_utc

    second = first.model_copy(update={"open_time_utc": start + timedelta(minutes=5)})
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD",
        timeframe="M5", candles=[second], timeframe_seconds=300, observed_at_utc=start,
    )
    changed = coordinator.validate_archive("XAUUSD")

    assert changed.cache_hit is False
    assert changed.completed_candles == 2
    assert changed.dataset_end_utc == start + timedelta(minutes=10)


def test_walk_forward_cache_does_not_hide_current_quote_status(tmp_path):
    database = tmp_path / "research.db"
    start = datetime(2026, 10, 1, tzinfo=UTC)
    store_completed_candles(
        database, source="MT5", broker_server="MetaQuotes-Demo", symbol="XAUUSD",
        timeframe="M5", candles=[Candle(
            open_time_utc=start, open=4000, high=4001, low=3999, close=4000.5,
            tick_volume=10, spread_points=3, completed=True,
        )], timeframe_seconds=300, observed_at_utc=start,
    )
    state = {"status": DataStatus.MARKET_CLOSED}
    adapter = SimpleNamespace(
        quote=lambda symbol: QuoteResponse(
            observed_at_utc=datetime.now(UTC), data_status=state["status"],
            symbol=symbol, point=0.01,
        ),
        connection=lambda symbol: SimpleNamespace(data_status=DataStatus.LIVE, broker_server="MetaQuotes-Demo"),
    )
    coordinator = BacktestCoordinator(adapter, database)

    coordinator.validate_archive("XAUUSD")
    state["status"] = DataStatus.LIVE
    repeated = coordinator.validate_archive("XAUUSD")

    assert repeated.cache_hit is True
    assert repeated.data_status == DataStatus.LIVE

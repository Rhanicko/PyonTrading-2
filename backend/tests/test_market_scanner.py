from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.schemas.market import Candle, DataStatus, QuoteResponse


class ScannerAdapter:
    def research_instruments(self):
        return DataStatus.LIVE, [], [
            {"symbol": "EURUSD.x", "base_currency": "EUR", "quote_currency": "USD"},
            {"symbol": "USDJPY.x", "base_currency": "USD", "quote_currency": "JPY"},
        ]

    def quote(self, symbol):
        return QuoteResponse(observed_at_utc=datetime.now(UTC), source_timestamp_utc=datetime.now(UTC),
                             data_status=DataStatus.LIVE, symbol=symbol, bid=100, ask=100.01,
                             tick_age_seconds=0.2, point=0.01, spread_points=1)

    def candles(self, symbol, timeframe, count):
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        values = [Candle(open_time_utc=now - timedelta(hours=60-i), open=100+i,
                         high=102+i, low=99+i, close=101+i, tick_volume=10, completed=i < 60)
                  for i in range(61)]
        return DataStatus.LIVE, [], values


def test_scanner_uses_exact_broker_metadata_and_observed_relative_strength():
    from app.services.scanner import MarketScanner

    result = MarketScanner(ScannerAdapter()).snapshot()
    assert {item.symbol for item in result.instruments} == {"EURUSD.x", "USDJPY.x"}
    strength = {item.currency: item for item in result.currency_strength}
    assert strength["EUR"].return_score_percent > 0
    assert strength["JPY"].return_score_percent < 0
    assert strength["USD"].pair_count == 2
    assert result.correlations[0].return_correlation == 1.0
    assert result.correlations[0].shared_return_bars == 20
    assert all(item.signal_authority is False for item in result.instruments)


def test_scanner_does_not_rank_stale_or_failed_history_and_does_not_cache_live_status():
    from app.services.scanner import MarketScanner

    adapter = ScannerAdapter()
    scanner = MarketScanner(adapter)
    assert len(scanner.snapshot().currency_strength) == 3
    original = adapter.quote
    adapter.quote = lambda symbol: original(symbol).model_copy(update={"data_status": DataStatus.STALE})
    stale = scanner.snapshot()
    assert stale.currency_strength == []
    assert stale.correlations == []
    assert all(item.comparison_rank is None for item in stale.instruments)


def test_scanner_correlates_only_shared_contiguous_timestamps():
    from app.services.scanner import MarketScanner

    adapter = ScannerAdapter()
    original = adapter.candles

    def shifted(symbol, timeframe, count):
        status, reasons, values = original(symbol, timeframe, count)
        if symbol == "USDJPY.x":
            values = [bar.model_copy(update={"open_time_utc": bar.open_time_utc - timedelta(days=3)}) for bar in values]
        return status, reasons, values

    adapter.candles = shifted
    result = MarketScanner(adapter).snapshot()
    assert result.correlations == []
    stale = next(item for item in result.instruments if item.symbol == "USDJPY.x")
    assert stale.comparison_rank is None


def test_scanner_route_is_bounded_and_rejects_undiscovered_symbols():
    from app.services.scanner import MarketScanner
    from app.api.routes import router

    app = FastAPI()
    app.include_router(router)
    app.state.market_scanner = MarketScanner(ScannerAdapter())
    app.state.live_service = SimpleNamespace(configured_symbol="EURUSD.x")
    with TestClient(app) as client:
        assert client.get("/api/market/scan?symbols=EURUSD.x").status_code == 200
        assert client.get("/api/market/scan?symbols=madeup").status_code == 422
        assert client.get("/api/market/scan?symbols=" + ",".join(["EURUSD.x"] * 9)).status_code == 422

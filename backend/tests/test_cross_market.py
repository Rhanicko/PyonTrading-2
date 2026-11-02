from datetime import UTC, datetime, timedelta

from app.schemas.market import Candle, DataStatus, QuoteResponse
from app.services.cross_market import CrossMarketContextService, CrossMarketSymbols


class ContextAdapter:
    def quote(self, symbol: str) -> QuoteResponse:
        now = datetime.now(UTC)
        return QuoteResponse(
            observed_at_utc=now,
            source_timestamp_utc=now,
            data_status=DataStatus.LIVE,
            symbol=symbol,
            bid=100.0,
            ask=100.1,
        )

    def candles(self, _symbol: str, _timeframe: str, _limit: int):
        now = datetime.now(UTC)
        bars = [
            Candle(
                open_time_utc=now - timedelta(hours=22 - index),
                open=100.0 + index,
                high=100.5 + index,
                low=99.5 + index,
                close=100.0 + index,
                tick_volume=10,
                completed=True,
            )
            for index in range(22)
        ]
        return DataStatus.LIVE, ["COMPLETED_CANDLES_ONLY"], bars


def test_context_symbols_can_be_updated_without_recreating_the_service():
    service = CrossMarketContextService(ContextAdapter(), CrossMarketSymbols())

    initial = service.snapshot()
    assert all(feature.data_status == DataStatus.NOT_CONFIGURED for feature in initial)

    service.set_symbols(CrossMarketSymbols(dxy="DXY.broker"))
    updated = service.snapshot()
    dxy = next(feature for feature in updated if feature.key == "DXY")

    assert dxy.configured_symbol == "DXY.broker"
    assert dxy.data_status == DataStatus.LIVE
    assert dxy.return_20_bars_percent is not None
    assert "BROKER_CONTEXT_FEATURE" in dxy.reason_codes
    assert "CONTEXT_ONLY_NOT_CAUSAL" in dxy.reason_codes

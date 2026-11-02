from __future__ import annotations

from dataclasses import dataclass

from app.adapters.mt5 import MT5Adapter
from app.schemas.market import CrossMarketFeature, DataStatus


@dataclass(frozen=True)
class CrossMarketSymbols:
    dxy: str | None = None
    us10y: str | None = None
    wti: str | None = None
    volatility: str | None = None

    def entries(self) -> tuple[tuple[str, str | None], ...]:
        return (("DXY", self.dxy), ("US10Y", self.us10y), ("WTI", self.wti), ("VOLATILITY", self.volatility))


class CrossMarketContextService:
    """Read configured broker symbols as contextual features, never causal proof."""

    def __init__(self, adapter: MT5Adapter, symbols: CrossMarketSymbols) -> None:
        self.adapter = adapter
        self.symbols = symbols

    def set_symbols(self, symbols: CrossMarketSymbols) -> None:
        """Apply exact locally validated symbols without creating an execution path."""
        self.symbols = symbols

    def snapshot(self) -> list[CrossMarketFeature]:
        values: list[CrossMarketFeature] = []
        for key, symbol in self.symbols.entries():
            if not symbol:
                values.append(CrossMarketFeature(
                    key=key, configured_symbol=None, data_status=DataStatus.NOT_CONFIGURED,
                    summary="No exact broker symbol is configured for this contextual feature.",
                    reason_codes=["CROSS_MARKET_SYMBOL_NOT_CONFIGURED", "CONTEXT_ONLY"],
                ))
                continue
            quote = self.adapter.quote(symbol)
            if quote.data_status != DataStatus.LIVE:
                values.append(CrossMarketFeature(
                    key=key, configured_symbol=symbol, data_status=quote.data_status,
                    source_timestamp_utc=quote.source_timestamp_utc,
                    summary="Configured broker context is unavailable; it is not substituted with another feed.",
                    reason_codes=[*quote.reason_codes, "CROSS_MARKET_CONTEXT_UNAVAILABLE", "CONTEXT_ONLY"],
                ))
                continue
            status, reasons, candles = self.adapter.candles(symbol, "H1", 22)
            completed = [bar for bar in candles if bar.completed]
            change = None
            if status == DataStatus.LIVE and len(completed) >= 21 and completed[-21].close:
                change = (completed[-1].close - completed[-21].close) / completed[-21].close * 100
            reason_codes = [*quote.reason_codes, *reasons, "BROKER_CONTEXT_FEATURE", "CONTEXT_ONLY_NOT_CAUSAL"]
            if change is None:
                reason_codes.append("CONTEXT_HISTORY_INSUFFICIENT")
            values.append(CrossMarketFeature(
                key=key, configured_symbol=symbol,
                data_status=DataStatus.LIVE if status == DataStatus.LIVE else status,
                source_timestamp_utc=quote.source_timestamp_utc,
                return_20_bars_percent=change,
                summary=(
                    "Broker-context return over 20 completed H1 bars. It is contextual evidence only."
                    if change is not None else "Current broker quote is live, but 20 completed H1 context bars are unavailable."
                ),
                reason_codes=list(dict.fromkeys(reason_codes)),
            ))
        return values

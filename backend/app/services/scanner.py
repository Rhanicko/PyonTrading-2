from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import combinations
from math import isfinite
from statistics import StatisticsError, correlation, mean

from app.analysis.technical import analyze_completed_candles
from app.schemas.market import CurrencyStrength, DataStatus, MarketCorrelation, MarketScanResponse, ScannedInstrument


class MarketScanner:
    """Bounded comparative context over exact visible broker instruments; no signal publication."""

    def __init__(self, adapter) -> None:
        self.adapter = adapter

    def snapshot(self, symbols: list[str] | None = None, preferred_symbol: str | None = None) -> MarketScanResponse:
        now = datetime.now(UTC)
        status, reasons, discovered = self.adapter.research_instruments()
        connection_reader = getattr(self.adapter, "connection", None)
        connection = connection_reader(preferred_symbol) if callable(connection_reader) else None
        by_symbol = {item["symbol"]: item for item in discovered}
        if symbols is not None and (len(symbols) > 8 or any(symbol not in by_symbol for symbol in symbols)):
            raise ValueError("EXACT_VISIBLE_BROKER_SYMBOL_REQUIRED_MAX_8")
        selected = symbols if symbols is not None else self._defaults(discovered, preferred_symbol)
        rows: list[ScannedInstrument] = []
        returns: dict[str, dict[datetime, float]] = {}
        strength: dict[str, list[float]] = {}
        for symbol in dict.fromkeys(selected):
            identity = by_symbol[symbol]
            row = ScannedInstrument(**identity, data_status=DataStatus.SOURCE_ERROR)
            try:
                quote = self.adapter.quote(symbol)
                row.data_status, row.source_timestamp_utc = quote.data_status, quote.source_timestamp_utc
                if quote.data_status != DataStatus.LIVE:
                    row.reason_codes = [*quote.reason_codes, "QUOTE_NOT_LIVE"]
                    rows.append(row)
                    continue
                history_status, history_reasons, values = self.adapter.candles(symbol, "H1", 61)
                completed = [bar for bar in values if bar.completed]
                last_close = completed[-1].open_time_utc + timedelta(hours=1) if completed else None
                row.candle_close_utc = last_close
                ordered = all(b.open_time_utc > a.open_time_utc for a, b in zip(completed, completed[1:]))
                fresh = last_close and timedelta(seconds=-2) <= now - last_close <= timedelta(hours=1, minutes=1)
                if history_status != DataStatus.LIVE or len(completed) < 60 or not ordered or not fresh:
                    row.data_status = history_status if history_status != DataStatus.LIVE else DataStatus.HISTORY_INSUFFICIENT if len(completed) < 60 else DataStatus.STALE if not fresh else DataStatus.SOURCE_ERROR
                    row.reason_codes = [*history_reasons, "CURRENT_ORDERED_H1_HISTORY_REQUIRED"]
                    rows.append(row)
                    continue
                technical = analyze_completed_candles(completed, timedelta(hours=1))
                start, end = completed[-21], completed[-1]
                if not all(isfinite(bar.close) and bar.close > 0 for bar in completed) or not technical.atr_14 or technical.atr_14 <= 0:
                    row.reason_codes = ["PRICE_OR_VOLATILITY_UNAVAILABLE"]
                    row.data_status = DataStatus.SOURCE_ERROR
                    rows.append(row)
                    continue
                row.return_20_bars_percent = (end.close / start.close - 1) * 100
                row.atr_percent = technical.atr_14 / end.close * 100
                row.spread_atr_ratio = (quote.ask - quote.bid) / technical.atr_14 if quote.ask is not None and quote.bid is not None else None
                row.structure = technical.trend_context
                row.market_regime = "TREND" if technical.adx_14 is not None and technical.adx_14 >= 20 else "RANGE_OR_WEAK_TREND"
                row.reason_codes = ["COMPLETED_H1_CONTEXT", "RANK_NOT_PROBABILITY", "NO_SIGNAL_AUTHORITY", "BROKER_TICK_PROXY"]
                if any(b.open_time_utc - a.open_time_utc != timedelta(hours=1) for a, b in zip(completed[-21:], completed[-20:])):
                    row.reason_codes.append("H1_WINDOW_GAPS_RETURN_NOT_20_CLOCK_HOURS")
                else:
                    returns[symbol] = {b.open_time_utc: b.close / a.close - 1 for a, b in zip(completed[-21:], completed[-20:])}
                strength.setdefault(row.base_currency, []).append(row.return_20_bars_percent)
                strength.setdefault(row.quote_currency, []).append(-row.return_20_bars_percent)
            except Exception as error:
                row.data_status = DataStatus.SOURCE_ERROR
                row.reason_codes = ["SCANNER_SOURCE_FAILED", type(error).__name__]
            rows.append(row)
        rankable = [row for row in rows if row.data_status == DataStatus.LIVE and row.atr_percent and row.return_20_bars_percent is not None]
        for rank, row in enumerate(sorted(rankable, key=lambda row: (-abs(row.return_20_bars_percent) / row.atr_percent, row.symbol)), 1):
            row.comparison_rank = rank
        correlations = []
        for first, second in combinations(returns, 2):
            shared = sorted(returns[first].keys() & returns[second].keys())
            if len(shared) < 20:
                continue
            try:
                value = correlation([returns[first][key] for key in shared], [returns[second][key] for key in shared])
            except StatisticsError:
                continue
            first_currencies = {by_symbol[first]["base_currency"], by_symbol[first]["quote_currency"]}
            second_currencies = {by_symbol[second]["base_currency"], by_symbol[second]["quote_currency"]}
            overlap = sorted(first_currencies & second_currencies)
            correlations.append(MarketCorrelation(first_symbol=first, second_symbol=second, return_correlation=round(value, 6), shared_return_bars=len(shared), shared_currencies=overlap, overlapping_exposure=bool(overlap) or abs(value) >= 0.8))
        return MarketScanResponse(
            observed_at_utc=now, data_status=DataStatus.LIVE if rankable else status if status != DataStatus.LIVE else DataStatus.HISTORY_INSUFFICIENT,
            broker_server=getattr(connection, "broker_server", None),
            source_timestamp_utc=min((row.candle_close_utc for row in rankable), default=None),
            instruments=sorted(rows, key=lambda row: (row.comparison_rank or 999, row.symbol)),
            currency_strength=[CurrencyStrength(currency=currency, return_score_percent=mean(values), pair_count=len(values)) for currency, values in sorted(strength.items())],
            correlations=correlations,
            reason_codes=[*reasons, "VISIBLE_BROKER_INSTRUMENTS_ONLY", "CURRENCY_SCORES_SAMPLE_DEPENDENT", "RETURN_CORRELATION_NOT_CAUSATION", "NO_ORDER_EXECUTION"],
        )

    @staticmethod
    def _defaults(discovered, preferred):
        selected, pairs = [], set()
        for item in sorted(discovered, key=lambda item: (item["symbol"] != preferred, item["quote_currency"] != "USD", item["symbol"])):
            pair = (item["base_currency"], item["quote_currency"])
            if pair not in pairs:
                selected.append(item["symbol"])
                pairs.add(pair)
            if len(selected) == 8:
                break
        return selected

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.adapters.mt5 import MT5Adapter
from app.analysis.backtesting import run_backtest
from app.analysis.technical import completed_candles
from app.analysis.training import StrategyCalibration, calibrate_strategies
from app.schemas.market import BacktestResponse, WalkForwardResponse
from app.storage.database import read_completed_candles, record_backtest_run


BACKTEST_ARCHIVE_LIMIT = 6_000
WALK_FORWARD_ARCHIVE_LIMIT = 50_000


class BacktestCoordinator:
    """Runs bounded, read-only historical research using MT5 broker candles."""

    def __init__(self, adapter: MT5Adapter, database_path: Path) -> None:
        self.adapter = adapter
        self.database_path = database_path
        self._validation_lock = Lock()
        self._validation_cache_key: tuple[str, str, float, int, datetime, datetime] | None = None
        self._validation_cache_result: tuple[list[StrategyCalibration], tuple[str, ...]] | None = None

    def validate_archive(self, symbol: str | None) -> WalkForwardResponse:
        """Read the active broker's completed archive for review-only chronological validation."""
        now = datetime.now(UTC)
        quote = self.adapter.quote(symbol)
        broker_server: str | None = None
        if symbol:
            try:
                connection = self.adapter.connection(symbol)
                if connection.data_status.value == "LIVE":
                    broker_server = connection.broker_server
            except Exception:
                pass
        candles = read_completed_candles(
            self.database_path, symbol=symbol, timeframe="M5", broker_server=broker_server,
            limit=WALK_FORWARD_ARCHIVE_LIMIT,
        ) if symbol and broker_server else []
        point = quote.point if quote.point and quote.point > 0 else None
        cache_hit = False
        if candles and point is not None and broker_server and symbol:
            # Stored completed candles are immutable for a broker/timeframe/open time.
            # Count and endpoints also change when the bounded 50k window advances.
            cache_key = (symbol, broker_server, point, len(candles), candles[0].open_time_utc, candles[-1].open_time_utc)
            with self._validation_lock:
                if cache_key == self._validation_cache_key and self._validation_cache_result is not None:
                    calibrations, calibration_reasons = self._validation_cache_result
                    cache_hit = True
                else:
                    calibrations, calibration_reasons = calibrate_strategies(candles, point)
                    self._validation_cache_key = cache_key
                    self._validation_cache_result = (calibrations, calibration_reasons)
        else:
            calibrations, calibration_reasons = calibrate_strategies(candles, point)
        reasons = ["CHRONOLOGICAL_60_20_20_SPLIT", "NO_MODEL_PROMOTION", "NO_ORDER_EXECUTION"]
        if not broker_server:
            reasons.append("BROKER_IDENTITY_UNAVAILABLE")
        elif not candles:
            reasons.append("NO_ACTIVE_BROKER_ARCHIVE")
        else:
            reasons.extend(["LOCAL_ARCHIVE_ACTIVE_BROKER_ONLY", f"WALK_FORWARD_ARCHIVE_LIMIT_{WALK_FORWARD_ARCHIVE_LIMIT}"])
        reasons.extend(calibration_reasons)
        return WalkForwardResponse(
            observed_at_utc=now,
            source_timestamp_utc=candles[-1].open_time_utc + timedelta(minutes=5) if candles else quote.source_timestamp_utc,
            data_status=quote.data_status,
            reason_codes=list(dict.fromkeys(reasons)),
            symbol=symbol, broker_server=broker_server,
            dataset_start_utc=candles[0].open_time_utc if candles else None,
            dataset_end_utc=candles[-1].open_time_utc + timedelta(minutes=5) if candles else None,
            completed_candles=len(candles),
            cache_hit=cache_hit,
            results=[asdict(item) for item in calibrations],
        )

    def run(self, symbol: str | None) -> BacktestResponse:
        now = datetime.now(UTC)
        quote = self.adapter.quote(symbol)
        completed = []
        candle_reasons: list[str] = []
        status = quote.data_status
        broker_server: str | None = None
        connection_reader = getattr(self.adapter, "connection", None)
        if callable(connection_reader):
            try:
                connection = connection_reader(symbol)
                if connection.data_status.value == "LIVE":
                    broker_server = connection.broker_server
            except Exception:
                candle_reasons.append("BROKER_SERVER_CHECK_FAILED")
        if symbol and broker_server is not None:
            completed = read_completed_candles(
                self.database_path, symbol=symbol, timeframe="M5",
                broker_server=broker_server, limit=BACKTEST_ARCHIVE_LIMIT,
            )
            if completed:
                status = quote.data_status
                candle_reasons.extend([
                    "LOCAL_ARCHIVE_ACTIVE_BROKER_ONLY",
                    f"BACKTEST_ARCHIVE_LIMIT_{BACKTEST_ARCHIVE_LIMIT}",
                ])
        if not completed:
            status, fetched_reasons, candles = self.adapter.candles(symbol, "M5", BACKTEST_ARCHIVE_LIMIT + 1)
            completed = completed_candles(candles)
            candle_reasons.extend([*fetched_reasons, "BACKTEST_CURRENT_MT5_HISTORY_FALLBACK"])
        point = quote.point if quote.point and quote.point > 0 else None
        results, _, backtest_reasons = run_backtest(completed, point)
        source_timestamp = completed[-1].open_time_utc + timedelta(minutes=5) if completed else quote.source_timestamp_utc
        reasons = [*candle_reasons, *backtest_reasons]
        if point is None:
            reasons.append("POINT_VALUE_UNAVAILABLE")
        response = BacktestResponse(
            observed_at_utc=now,
            source_timestamp_utc=source_timestamp,
            data_status=status,
            reason_codes=list(dict.fromkeys(reasons)),
            symbol=symbol,
            dataset_start_utc=completed[0].open_time_utc if completed else None,
            dataset_end_utc=source_timestamp,
            completed_candles=len(completed),
            results=[result.__dict__ for result in results],
            cost_model=(
                "Recorded entry-bar MT5 spread only; values are spread-adjusted, not net P&L. Commission, slippage, swap, and fill quality are unavailable."
                if point is not None else
                "Costs unavailable because broker point metadata is unavailable."
            ),
            limitation=(
                "Research replay only. No order was sent; spread-adjusted points are not net performance without commission, slippage, swap, and fill data."
            ),
        )
        if results and symbol:
            run_id = uuid4().hex
            response = response.model_copy(update={"run_id": run_id})
            record_backtest_run(
                self.database_path, run_id=run_id, created_at_utc=now, symbol=symbol, timeframe="M5",
                dataset_start_utc=response.dataset_start_utc, dataset_end_utc=response.dataset_end_utc,
                completed_candles=len(completed), data_status=status.value,
                reason_codes=response.reason_codes, payload=response.model_dump(mode="json"),
            )
        return response

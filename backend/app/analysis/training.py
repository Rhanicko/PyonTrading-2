from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from datetime import datetime

from app.analysis.backtesting import STRATEGY_CATALOG, BacktestTrade, HistoricalSignal, StrategyId, contiguous_segment_ids, evaluate_historical_signals
from app.analysis.technical import completed_candles
from app.schemas.market import Candle


MIN_TRAINING_CANDLES = 5_000
HOLD_CANDIDATES = (3, 6, 9, 12)


@dataclass(frozen=True)
class Metrics:
    trials: int
    wins: int
    losses: int
    gross_points: float
    net_points: float | None
    spread_adjusted_expectancy_points: float | None = None
    spread_adjusted_profit_factor: float | None = None
    spread_adjusted_max_drawdown_points: float | None = None
    spread_adjusted_win_rate_percent: float | None = None


@dataclass(frozen=True)
class RollingValidationFold:
    training_candles: int
    validation_start_utc: datetime
    validation_end_utc: datetime
    selected_hold_bars: int | None
    validation: Metrics


@dataclass(frozen=True)
class StrategyCalibration:
    strategy_id: StrategyId
    strategy_version: str
    selected_hold_bars: int | None
    training: Metrics
    validation: Metrics
    held_out: Metrics
    state: Literal["REVIEW_REQUIRED", "INSUFFICIENT_DATA"]
    reason_codes: tuple[str, ...]
    walk_forward: tuple[RollingValidationFold, ...] = ()


def _trades_for_hold(signals: list[HistoricalSignal], candles: list[Candle], point: float | None, hold_bars: int) -> list[BacktestTrade]:
    trades: list[BacktestTrade] = []
    segments = contiguous_segment_ids(candles)
    last_exit: dict[str, int] = {}
    for signal in signals:
        entry_index = signal.known_at_index + 1
        exit_index = entry_index + hold_bars - 1
        if exit_index >= len(candles):
            continue
        if segments[signal.known_at_index] != segments[exit_index]:
            continue
        if entry_index <= last_exit.get(signal.strategy_id, -1):
            continue
        entry, exit_candle = candles[entry_index], candles[exit_index]
        side = 1 if signal.direction == "LONG" else -1
        gross_points = side * (exit_candle.close - entry.open) / point if point else 0.0
        spread_cost = float(entry.spread_points) if point and entry.spread_points is not None else None
        trades.append(BacktestTrade(
            strategy_id=signal.strategy_id, direction=signal.direction, known_at_index=signal.known_at_index,
            entry_index=entry_index, exit_index=exit_index, gross_points=gross_points,
            net_points=gross_points - spread_cost if spread_cost is not None else None,
            spread_cost_points=spread_cost,
        ))
        last_exit[signal.strategy_id] = exit_index
    return trades


def _metrics(trades: list[BacktestTrade]) -> Metrics:
    cost_complete = bool(trades) and all(trade.net_points is not None for trade in trades)
    net = [trade.net_points for trade in trades] if cost_complete else []
    gains = sum(max(value, 0) for value in net)
    losses = -sum(min(value, 0) for value in net)
    equity = peak = drawdown = 0.0
    for value in net:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return Metrics(
        trials=len(trades), wins=sum(trade.gross_points > 0 for trade in trades),
        losses=sum(trade.gross_points < 0 for trade in trades),
        gross_points=sum(trade.gross_points for trade in trades),
        net_points=sum(trade.net_points for trade in trades) if cost_complete else None,
        spread_adjusted_expectancy_points=sum(net) / len(net) if net else None,
        spread_adjusted_profit_factor=gains / losses if losses else None,
        spread_adjusted_max_drawdown_points=drawdown if cost_complete else None,
        spread_adjusted_win_rate_percent=sum(value > 0 for value in net) / len(net) * 100 if net else None,
    )


def calibrate_strategies(candles: list[Candle], point: float | None) -> tuple[list[StrategyCalibration], tuple[str, ...]]:
    """Chronologically tune only holding horizon; never use validation/test data to select it."""
    values = completed_candles(candles)
    if len(values) < MIN_TRAINING_CANDLES:
        return [], ("TRAINING_HISTORY_INSUFFICIENT", "NO_MODEL_PROMOTION")
    if point is None:
        return [], ("POINT_VALUE_UNAVAILABLE", "COSTS_INCOMPLETE", "NO_MODEL_PROMOTION")

    signals = evaluate_historical_signals(values)
    train_end = int(len(values) * 0.60)
    validation_end = int(len(values) * 0.80)
    results: list[StrategyCalibration] = []
    # Every catalogue member receives a versioned calibration record. Strategies
    # that require a source not present in broker candles deliberately remain
    # insufficient instead of inheriting a price-only result.
    strategies: tuple[tuple[StrategyId, str], ...] = tuple(
        (strategy_id, version) for strategy_id, version, _source_label in STRATEGY_CATALOG
    )
    for strategy_id, version in strategies:
        strategy_signals = [signal for signal in signals if signal.strategy_id == strategy_id]
        candidates: list[tuple[int, Metrics, list[BacktestTrade]]] = []
        horizon_trials: dict[int, list[BacktestTrade]] = {}
        for hold_bars in HOLD_CANDIDATES:
            trades = _trades_for_hold(strategy_signals, values, point, hold_bars)
            horizon_trials[hold_bars] = trades
            training_trades = [trade for trade in trades if trade.exit_index < train_end]
            metrics = _metrics(training_trades)
            if metrics.net_points is not None and metrics.trials >= 10:
                candidates.append((hold_bars, metrics, trades))
        if not candidates:
            empty = Metrics(0, 0, 0, 0.0, None)
            results.append(StrategyCalibration(
                strategy_id=strategy_id, strategy_version=version, selected_hold_bars=None,
                training=empty, validation=empty, held_out=empty, state="INSUFFICIENT_DATA",
                reason_codes=("INSUFFICIENT_TRAINING_TRIALS_OR_COST_DATA", "NO_MODEL_PROMOTION"),
            ))
            continue
        selected_hold, training_metrics, selected_trades = max(candidates, key=lambda item: (item[1].net_points, item[1].trials))
        validation_metrics = _metrics([
            trade for trade in selected_trades
            if train_end <= trade.known_at_index and trade.exit_index < validation_end
        ])
        held_out_metrics = _metrics([trade for trade in selected_trades if trade.known_at_index >= validation_end])
        folds = []
        # All fold selection/evaluation ends before the untouched final 20%.
        for train_fraction, end_fraction in ((0.4, 0.5), (0.5, 0.6), (0.6, 0.8)):
            fold_train_end, fold_end = int(len(values) * train_fraction), int(len(values) * end_fraction)
            options = [(hold, _metrics([trade for trade in trials if trade.exit_index < fold_train_end])) for hold, trials in horizon_trials.items()]
            options = [(hold, metric) for hold, metric in options if metric.trials >= 10 and metric.net_points is not None]
            hold = max(options, key=lambda item: (item[1].net_points, item[1].trials))[0] if options else None
            fold_trials = [trade for trade in horizon_trials[hold] if fold_train_end <= trade.known_at_index and trade.exit_index < fold_end] if hold else []
            folds.append(RollingValidationFold(
                training_candles=fold_train_end, validation_start_utc=values[fold_train_end].open_time_utc,
                validation_end_utc=values[fold_end - 1].open_time_utc, selected_hold_bars=hold, validation=_metrics(fold_trials),
            ))
        results.append(StrategyCalibration(
            strategy_id=strategy_id, strategy_version=version, selected_hold_bars=selected_hold,
            training=training_metrics, validation=validation_metrics, held_out=held_out_metrics,
            state="REVIEW_REQUIRED",
            walk_forward=tuple(folds),
            reason_codes=(
                "CHRONOLOGICAL_60_20_20_SPLIT", "HELD_OUT_NOT_USED_FOR_SELECTION",
                "COMMISSION_UNAVAILABLE", "NO_MODEL_PROMOTION", "NO_ORDER_EXECUTION",
                "NON_OVERLAPPING_TRIALS_PER_STRATEGY", "THREE_EXPANDING_VALIDATION_FOLDS_BEFORE_FINAL_HOLDOUT",
                "DRAWDOWN_IN_POINTS_NOT_PORTFOLIO_EQUITY", "SPREAD_ADJUSTED_NOT_NET_PNL",
            ),
        ))
    return results, ("CALIBRATION_RESEARCH_ONLY", "COMMISSION_UNAVAILABLE", "NO_MODEL_PROMOTION", "NO_ORDER_EXECUTION")

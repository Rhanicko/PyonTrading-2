from datetime import UTC, datetime, timedelta

from app.analysis.backtesting import HistoricalSignal, evaluate_historical_signals
from app.analysis.training import MIN_TRAINING_CANDLES, _trades_for_hold, calibrate_strategies
from app.analysis.training import _metrics
from app.analysis.backtesting import BacktestTrade
import pytest
from app.schemas.market import Candle


def history(count: int) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    values = []
    price = 4000.0
    for index in range(count):
        price += 0.7 + (0.35 if index % 13 == 0 else -0.1 if index % 17 == 0 else 0)
        values.append(Candle(
            open_time_utc=start + timedelta(minutes=index * 5), open=price - 0.4,
            high=price + 0.8, low=price - 1.0, close=price, tick_volume=10,
            spread_points=3, completed=True,
        ))
    return values


def test_calibration_trials_do_not_open_overlapping_positions_for_one_strategy():
    values = history(100)
    signals = [HistoricalSignal(strategy_id="PRICE_STRUCTURE_BASELINE", strategy_version="v1", direction="LONG",
                                known_at_index=index, source_bar_time=values[index].open_time_utc, reason_codes=())
               for index in [80, 86, 92]]
    trades = _trades_for_hold(signals, values, 0.01, 12)
    assert [trade.known_at_index for trade in trades] == [80]


def test_validation_metrics_use_recorded_spread_and_preserve_missing_costs():
    trades = [BacktestTrade(strategy_id="PRICE_STRUCTURE_BASELINE", direction="LONG", known_at_index=i,
                            entry_index=i+1, exit_index=i+2, gross_points=gross, net_points=net, spread_cost_points=2)
              for i, (gross, net) in enumerate([(10, 8), (-5, -7), (2, 0), (-2, -4)])]
    result = _metrics(trades)
    assert result.spread_adjusted_expectancy_points == -0.75
    assert result.spread_adjusted_profit_factor == pytest.approx(8 / 11)
    assert result.spread_adjusted_max_drawdown_points == 11
    assert result.spread_adjusted_win_rate_percent == 25
    missing = _metrics([BacktestTrade(strategy_id="PRICE_STRUCTURE_BASELINE", direction="LONG", known_at_index=0,
                                      entry_index=1, exit_index=2, gross_points=10, net_points=None, spread_cost_points=None)])
    assert missing.spread_adjusted_profit_factor is None
    assert missing.spread_adjusted_expectancy_points is None


def test_calibration_refuses_short_history_and_missing_point_metadata():
    result, reasons = calibrate_strategies(history(MIN_TRAINING_CANDLES - 1), 0.01)
    assert result == []
    assert reasons[0] == "TRAINING_HISTORY_INSUFFICIENT"

    result, reasons = calibrate_strategies(history(MIN_TRAINING_CANDLES), None)
    assert result == []
    assert "POINT_VALUE_UNAVAILABLE" in reasons


def test_calibration_keeps_held_out_data_out_of_parameter_selection():
    result, reasons = calibrate_strategies(history(MIN_TRAINING_CANDLES), 0.01)

    assert len(result) == 9
    assert "CALIBRATION_RESEARCH_ONLY" in reasons
    assert all(item.state in {"REVIEW_REQUIRED", "INSUFFICIENT_DATA"} for item in result)
    assert all("NO_MODEL_PROMOTION" in item.reason_codes for item in result)
    comparable = [item for item in result if item.selected_hold_bars is not None]
    assert comparable
    end_of_validation = history(MIN_TRAINING_CANDLES)[int(MIN_TRAINING_CANDLES * 0.8)].open_time_utc
    for item in comparable:
        assert len(item.walk_forward) == 3
        assert [fold.training_candles for fold in item.walk_forward] == [2000, 2500, 3000]
        assert all(fold.validation_end_utc < end_of_validation for fold in item.walk_forward)
    futures_flow = next(item for item in result if item.strategy_id == "ORDER_FLOW_FUTURES_CONFIRMATION")
    assert futures_flow.state == "INSUFFICIENT_DATA"


def test_calibration_excludes_outcomes_crossing_chronological_partitions():
    values = history(MIN_TRAINING_CANDLES)
    calibrations, _ = calibrate_strategies(values, 0.01)
    signals = evaluate_historical_signals(values)
    train_end = int(len(values) * 0.60)
    validation_end = int(len(values) * 0.80)
    selected = [item for item in calibrations if item.selected_hold_bars is not None]

    assert selected
    for item in selected:
        trades = [
            trade for trade in _trades_for_hold(signals, values, 0.01, item.selected_hold_bars)
            if trade.strategy_id == item.strategy_id
        ]
        assert item.training.trials == sum(trade.exit_index < train_end for trade in trades)
        assert item.validation.trials == sum(
            train_end <= trade.known_at_index and trade.exit_index < validation_end
            for trade in trades
        )


def test_training_excludes_trials_that_cross_missing_candle_intervals():
    values = [
        bar.model_copy(update={"open_time_utc": bar.open_time_utc + timedelta(hours=2)})
        if index >= 100 else bar
        for index, bar in enumerate(history(180))
    ]
    signals = [HistoricalSignal(
        strategy_id="PRICE_STRUCTURE_BASELINE", strategy_version="price-structure-baseline-v1",
        direction="LONG", known_at_index=96, source_bar_time=values[96].open_time_utc,
        reason_codes=("COMPLETED_CANDLES_ONLY",),
    )]

    trades = _trades_for_hold(signals, values, 0.01, 6)

    assert trades == []

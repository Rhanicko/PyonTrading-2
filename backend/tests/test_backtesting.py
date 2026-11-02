from datetime import UTC, datetime, timedelta

from app.analysis.backtesting import HOLD_BARS, LOOKBACK_BARS, evaluate_historical_signals, run_backtest
from app.schemas.market import Candle


def candle(index: int, close: float, completed: bool = True) -> Candle:
    open_price = close - 0.3
    return Candle(
        open_time_utc=datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=index * 5),
        open=open_price, high=close + 0.8, low=open_price - 0.6, close=close,
        tick_volume=10, spread_points=3, completed=completed,
    )


def trending_candles(count: int = 180) -> list[Candle]:
    values = []
    price = 4000.0
    for index in range(count):
        price += 0.8 + (0.25 if index % 9 == 0 else 0)
        values.append(candle(index, price))
    return values


def test_backtest_uses_next_bar_after_a_signal_and_records_cost_limitations():
    values = trending_candles()

    results, trades, reasons = run_backtest(values, point=0.01)

    assert len(results) == 9
    assert all(trade.entry_index == trade.known_at_index + 1 for trade in trades)
    assert all(trade.exit_index == trade.entry_index + HOLD_BARS for trade in trades)
    assert "COMMISSION_UNAVAILABLE" in reasons
    assert all("NO_ORDER_EXECUTION" in result.reason_codes for result in results)
    futures_only = next(result for result in results if result.strategy_id == "ORDER_FLOW_FUTURES_CONFIRMATION")
    profile_proxy = next(result for result in results if result.strategy_id == "VOLUME_PROFILE_PROXY_AUCTION")
    assert futures_only.completed_trials == 0
    assert "LICENSED_FUTURES_DATA_REQUIRED" in futures_only.reason_codes
    assert profile_proxy.completed_trials == 0
    assert "PROXY_NOT_TRADE_AT_PRICE" in profile_proxy.reason_codes


def test_backtest_never_observes_a_forming_candle_or_generates_a_trade_without_history():
    values = trending_candles(LOOKBACK_BARS + HOLD_BARS)
    forming = candle(len(values), 9999, completed=False)

    assert evaluate_historical_signals([*values, forming]) == evaluate_historical_signals(values)
    results, trades, reasons = run_backtest([*values, forming], point=0.01)
    assert results == [] and trades == []
    assert reasons[0] == "HISTORY_INSUFFICIENT"


def test_backtest_uses_a_bounded_rolling_context():
    values = trending_candles(1_000)

    signals = evaluate_historical_signals(values)

    assert all(signal.known_at_index >= LOOKBACK_BARS - 1 for signal in signals)


def test_missing_spread_does_not_create_a_net_result():
    values = [item.model_copy(update={"spread_points": None}) for item in trending_candles()]

    results, _, _ = run_backtest(values, point=0.01)

    assert all(result.net_points is None for result in results)
    assert all("COSTS_INCOMPLETE" in result.reason_codes for result in results)

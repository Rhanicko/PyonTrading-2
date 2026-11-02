from datetime import UTC, datetime, timedelta

from app.analysis.training import MIN_TRAINING_CANDLES, calibrate_strategies
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
    futures_flow = next(item for item in result if item.strategy_id == "ORDER_FLOW_FUTURES_CONFIRMATION")
    assert futures_flow.state == "INSUFFICIENT_DATA"

from datetime import UTC, datetime, timedelta

from app.analysis.technical import analyze_completed_candles, confirmed_swings, fair_value_gaps, structure_events
from app.schemas.market import Candle


FIVE_MINUTES = timedelta(minutes=5)


def bar(index: int, *, high: float, low: float, close: float, completed: bool = True) -> Candle:
    return Candle(
        open_time_utc=datetime(2026, 10, 21, tzinfo=UTC) + (FIVE_MINUTES * index),
        open=(high + low) / 2, high=high, low=low, close=close, tick_volume=1, completed=completed,
    )


def test_swing_is_not_available_until_its_confirmation_bar_has_closed():
    candles = [
        bar(0, high=10, low=5, close=7), bar(1, high=11, low=6, close=8),
        bar(2, high=15, low=7, close=9), bar(3, high=12, low=6, close=8),
        bar(4, high=11, low=5, close=7),
    ]

    assert confirmed_swings(candles[:4], FIVE_MINUTES) == []

    swings = confirmed_swings(candles, FIVE_MINUTES)
    high = next(swing for swing in swings if swing.kind == "HIGH")
    assert high.source_bar_time == candles[2].open_time_utc
    assert high.confirmation_bar_time == candles[4].open_time_utc
    assert high.known_at == candles[4].open_time_utc + FIVE_MINUTES


def test_structure_break_waits_for_an_already_known_swing_level():
    candles = [
        bar(0, high=10, low=5, close=7), bar(1, high=11, low=6, close=8),
        bar(2, high=15, low=7, close=9), bar(3, high=12, low=6, close=8),
        bar(4, high=11, low=5, close=7), bar(5, high=16, low=8, close=16),
    ]
    swings = confirmed_swings(candles, FIVE_MINUTES)
    events = structure_events(candles, swings, FIVE_MINUTES)

    assert len(events) == 1
    assert events[0].kind == "BOS"
    assert events[0].direction == "BULLISH"
    assert events[0].detected_at == candles[5].open_time_utc + FIVE_MINUTES
    assert events[0].detected_at > events[0].confirmation_bar_time


def test_fair_value_gap_is_known_only_after_the_third_completed_candle():
    candles = [
        bar(0, high=10, low=8, close=9), bar(1, high=12, low=9, close=11),
        bar(2, high=14, low=11, close=13),
    ]

    assert fair_value_gaps(candles[:2], FIVE_MINUTES) == []
    gap = fair_value_gaps(candles, FIVE_MINUTES)[0]
    assert gap.direction == "BULLISH"
    assert (gap.lower_price, gap.upper_price) == (10, 11)
    assert gap.known_at == candles[2].open_time_utc + FIVE_MINUTES


def test_forming_candle_cannot_change_technical_snapshot():
    completed = [bar(index, high=100 + index, low=98 + index, close=99 + index) for index in range(70)]
    forming = bar(70, high=500, low=1, close=400, completed=False)

    baseline = analyze_completed_candles(completed, FIVE_MINUTES)
    with_forming = analyze_completed_candles([*completed, forming], FIVE_MINUTES)

    assert with_forming == baseline
    assert baseline.ema_20 is not None and baseline.ema_60 is not None
    assert baseline.atr_14 is not None and baseline.rsi_14 is not None
    assert baseline.sma_20 is not None
    assert baseline.macd_line is not None and baseline.macd_signal is not None and baseline.macd_histogram is not None
    assert baseline.adx_14 is not None
    assert baseline.bollinger_middle is not None and baseline.bollinger_upper is not None and baseline.bollinger_lower is not None
    assert baseline.roc_10 is not None and baseline.realized_volatility_20 is not None


def test_fair_value_gap_mitigation_uses_only_a_later_completed_candle():
    candles = [
        bar(0, high=10, low=8, close=9), bar(1, high=12, low=9, close=11),
        bar(2, high=14, low=11, close=13), bar(3, high=13, low=9, close=10),
    ]

    gap = fair_value_gaps(candles, FIVE_MINUTES)[0]
    assert gap.invalidated_at == candles[3].open_time_utc + FIVE_MINUTES

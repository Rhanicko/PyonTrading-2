from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import log, sqrt
from typing import Literal

from app.schemas.market import Candle


Direction = Literal["BULLISH", "BEARISH"]
StructureKind = Literal["BOS", "CHOCH"]


@dataclass(frozen=True)
class ConfirmedSwing:
    kind: Literal["HIGH", "LOW"]
    price: float
    source_bar_time: datetime
    confirmation_bar_time: datetime
    known_at: datetime
    label: str


@dataclass(frozen=True)
class StructureEvent:
    kind: StructureKind
    direction: Direction
    level: float
    source_bar_time: datetime
    confirmation_bar_time: datetime
    detected_at: datetime
    known_at: datetime
    invalidated_at: datetime | None = None


@dataclass(frozen=True)
class FairValueGap:
    direction: Direction
    lower_price: float
    upper_price: float
    source_bar_time: datetime
    confirmation_bar_time: datetime
    detected_at: datetime
    known_at: datetime
    invalidated_at: datetime | None = None


@dataclass(frozen=True)
class TechnicalSnapshot:
    candle_count: int
    sma_20: float | None
    ema_20: float | None
    ema_60: float | None
    rsi_14: float | None
    atr_14: float | None
    macd_line: float | None
    macd_signal: float | None
    macd_histogram: float | None
    adx_14: float | None
    bollinger_middle: float | None
    bollinger_upper: float | None
    bollinger_lower: float | None
    roc_10: float | None
    realized_volatility_20: float | None
    swings: tuple[ConfirmedSwing, ...]
    structure_events: tuple[StructureEvent, ...]
    fair_value_gaps: tuple[FairValueGap, ...]

    @property
    def trend_context(self) -> str:
        if self.ema_20 is None or self.ema_60 is None:
            return "UNAVAILABLE"
        if self.ema_20 > self.ema_60:
            return "EMA_BULLISH"
        if self.ema_20 < self.ema_60:
            return "EMA_BEARISH"
        return "EMA_FLAT"


def completed_candles(candles: list[Candle]) -> list[Candle]:
    """Return chronologically ordered completed candles only.

    The MT5 adapter marks its final returned bar as forming. Analysis must not
    promote that bar to evidence, even if an upstream caller includes it.
    """
    return sorted((candle for candle in candles if candle.completed), key=lambda candle: candle.open_time_utc)


def ema(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    result = sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    for value in values[period:]:
        result = (value - result) * multiplier + result
    return result


def sma(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(values: list[float], period: int = 14) -> float | None:
    if period <= 0 or len(values) <= period:
        return None
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    average_gain = sum(max(change, 0) for change in changes[:period]) / period
    average_loss = sum(max(-change, 0) for change in changes[:period]) / period
    for change in changes[period:]:
        average_gain = ((average_gain * (period - 1)) + max(change, 0)) / period
        average_loss = ((average_loss * (period - 1)) + max(-change, 0)) / period
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100 - (100 / (1 + relative_strength))


def atr(candles: list[Candle], period: int = 14) -> float | None:
    if period <= 0 or len(candles) <= period:
        return None
    ranges = [
        max(candle.high - candle.low, abs(candle.high - previous.close), abs(candle.low - previous.close))
        for previous, candle in zip(candles, candles[1:])
    ]
    result = sum(ranges[:period]) / period
    for value in ranges[period:]:
        result = ((result * (period - 1)) + value) / period
    return result


def macd(values: list[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> tuple[float | None, float | None, float | None]:
    if min(fast_period, slow_period, signal_period) <= 0 or fast_period >= slow_period or len(values) < slow_period + signal_period - 1:
        return None, None, None
    lines = [
        fast - slow
        for index in range(slow_period - 1, len(values))
        if (fast := ema(values[:index + 1], fast_period)) is not None and (slow := ema(values[:index + 1], slow_period)) is not None
    ]
    signal = ema(lines, signal_period)
    if not lines or signal is None:
        return None, None, None
    return lines[-1], signal, lines[-1] - signal


def adx(candles: list[Candle], period: int = 14) -> float | None:
    """Return the final Wilder ADX value, or `None` for insufficient history."""
    if period <= 0 or len(candles) < (period * 2) + 1:
        return None
    true_ranges: list[float] = []
    plus_moves: list[float] = []
    minus_moves: list[float] = []
    for previous, current in zip(candles, candles[1:]):
        upward = current.high - previous.high
        downward = previous.low - current.low
        plus_moves.append(upward if upward > downward and upward > 0 else 0.0)
        minus_moves.append(downward if downward > upward and downward > 0 else 0.0)
        true_ranges.append(max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close)))

    smoothed_tr = sum(true_ranges[:period])
    smoothed_plus = sum(plus_moves[:period])
    smoothed_minus = sum(minus_moves[:period])
    dx_values: list[float] = []
    for index in range(period, len(true_ranges)):
        smoothed_tr = smoothed_tr - (smoothed_tr / period) + true_ranges[index]
        smoothed_plus = smoothed_plus - (smoothed_plus / period) + plus_moves[index]
        smoothed_minus = smoothed_minus - (smoothed_minus / period) + minus_moves[index]
        if smoothed_tr == 0:
            dx_values.append(0.0)
            continue
        plus_di = 100 * smoothed_plus / smoothed_tr
        minus_di = 100 * smoothed_minus / smoothed_tr
        denominator = plus_di + minus_di
        dx_values.append(0.0 if denominator == 0 else 100 * abs(plus_di - minus_di) / denominator)
    if len(dx_values) < period:
        return None
    value = sum(dx_values[:period]) / period
    for dx_value in dx_values[period:]:
        value = ((value * (period - 1)) + dx_value) / period
    return value


def bollinger_bands(values: list[float], period: int = 20, deviations: float = 2.0) -> tuple[float | None, float | None, float | None]:
    middle = sma(values, period)
    if middle is None:
        return None, None, None
    window = values[-period:]
    standard_deviation = sqrt(sum((value - middle) ** 2 for value in window) / period)
    return middle, middle + (deviations * standard_deviation), middle - (deviations * standard_deviation)


def rate_of_change(values: list[float], period: int = 10) -> float | None:
    if period <= 0 or len(values) <= period or values[-period - 1] == 0:
        return None
    return ((values[-1] / values[-period - 1]) - 1) * 100


def realized_volatility(values: list[float], period: int = 20) -> float | None:
    if period <= 1 or len(values) <= period or any(value <= 0 for value in values[-period - 1:]):
        return None
    returns = [log(current / previous) for previous, current in zip(values[-period - 1:], values[-period:])]
    mean = sum(returns) / len(returns)
    return sqrt(sum((value - mean) ** 2 for value in returns) / (len(returns) - 1))


def confirmed_swings(candles: list[Candle], timeframe: timedelta, left: int = 2, right: int = 2) -> list[ConfirmedSwing]:
    """Find local extrema only after `right` completed future bars exist.

    `known_at` is the close of the confirmation bar, not the pivot's timestamp.
    This makes a pivot unavailable to both historical replay and live decisions
    until the moment it could genuinely have been known.
    """
    values = completed_candles(candles)
    if left < 1 or right < 1:
        raise ValueError("left and right confirmation bars must be positive")
    swings: list[ConfirmedSwing] = []
    for index in range(left, len(values) - right):
        window = values[index - left:index + right + 1]
        candidate = values[index]
        other_highs = [bar.high for offset, bar in enumerate(window) if offset != left]
        other_lows = [bar.low for offset, bar in enumerate(window) if offset != left]
        confirmation = values[index + right]
        known_at = confirmation.open_time_utc + timeframe
        if candidate.high > max(other_highs):
            swings.append(ConfirmedSwing(
                kind="HIGH", price=candidate.high, source_bar_time=candidate.open_time_utc,
                confirmation_bar_time=confirmation.open_time_utc, known_at=known_at,
                label="SWING_HIGH",
            ))
        if candidate.low < min(other_lows):
            swings.append(ConfirmedSwing(
                kind="LOW", price=candidate.low, source_bar_time=candidate.open_time_utc,
                confirmation_bar_time=confirmation.open_time_utc, known_at=known_at,
                label="SWING_LOW",
            ))
    return sorted(swings, key=lambda swing: (swing.known_at, swing.kind))


def structure_events(candles: list[Candle], swings: list[ConfirmedSwing], timeframe: timedelta) -> list[StructureEvent]:
    """Detect completed-close breaks of already-confirmed swings.

    Only swing levels whose `known_at` is no later than a candle's open are
    eligible. This is the critical guard against accidental future leakage.
    """
    values = completed_candles(candles)
    events: list[StructureEvent] = []
    broken: set[tuple[str, datetime]] = set()
    bias: Direction | None = None
    last_close: float | None = None
    for candle in values:
        available = [swing for swing in swings if swing.known_at <= candle.open_time_utc]
        highs = [swing for swing in available if swing.kind == "HIGH"]
        lows = [swing for swing in available if swing.kind == "LOW"]
        if last_close is not None and highs:
            high = highs[-1]
            key = (high.kind, high.source_bar_time)
            if key not in broken and last_close <= high.price < candle.close:
                kind: StructureKind = "BOS" if bias in {None, "BULLISH"} else "CHOCH"
                events.append(StructureEvent(
                    kind=kind, direction="BULLISH", level=high.price, source_bar_time=high.source_bar_time,
                    confirmation_bar_time=high.confirmation_bar_time,
                    detected_at=candle.open_time_utc + timeframe, known_at=candle.open_time_utc + timeframe,
                ))
                broken.add(key)
                bias = "BULLISH"
        if last_close is not None and lows:
            low = lows[-1]
            key = (low.kind, low.source_bar_time)
            if key not in broken and last_close >= low.price > candle.close:
                kind = "BOS" if bias in {None, "BEARISH"} else "CHOCH"
                events.append(StructureEvent(
                    kind=kind, direction="BEARISH", level=low.price, source_bar_time=low.source_bar_time,
                    confirmation_bar_time=low.confirmation_bar_time,
                    detected_at=candle.open_time_utc + timeframe, known_at=candle.open_time_utc + timeframe,
                ))
                broken.add(key)
                bias = "BEARISH"
        last_close = candle.close
    return events


def fair_value_gaps(candles: list[Candle], timeframe: timedelta) -> list[FairValueGap]:
    """Detect three-candle gaps and mark only later completed mitigation."""
    values = completed_candles(candles)
    gaps: list[FairValueGap] = []
    for index in range(2, len(values)):
        first, _, third = values[index - 2:index + 1]
        direction: Direction | None = None
        lower = upper = 0.0
        if third.low > first.high:
            direction, lower, upper = "BULLISH", first.high, third.low
        elif third.high < first.low:
            direction, lower, upper = "BEARISH", third.high, first.low
        if direction is None:
            continue
        invalidated_at = None
        for later in values[index + 1:]:
            touched = later.low <= lower if direction == "BULLISH" else later.high >= upper
            if touched:
                invalidated_at = later.open_time_utc + timeframe
                break
        detected_at = third.open_time_utc + timeframe
        gaps.append(FairValueGap(
            direction=direction, lower_price=lower, upper_price=upper,
            source_bar_time=first.open_time_utc, confirmation_bar_time=third.open_time_utc,
            detected_at=detected_at, known_at=detected_at, invalidated_at=invalidated_at,
        ))
    return gaps


def analyze_completed_candles(candles: list[Candle], timeframe: timedelta) -> TechnicalSnapshot:
    """Create a reproducible technical snapshot from completed broker candles."""
    values = completed_candles(candles)
    closes = [candle.close for candle in values]
    swings = confirmed_swings(values, timeframe)
    macd_line, macd_signal, macd_histogram = macd(closes)
    bollinger_middle, bollinger_upper, bollinger_lower = bollinger_bands(closes)
    return TechnicalSnapshot(
        candle_count=len(values),
        sma_20=sma(closes, 20),
        ema_20=ema(closes, 20),
        ema_60=ema(closes, 60),
        rsi_14=rsi(closes, 14),
        atr_14=atr(values, 14),
        macd_line=macd_line,
        macd_signal=macd_signal,
        macd_histogram=macd_histogram,
        adx_14=adx(values, 14),
        bollinger_middle=bollinger_middle,
        bollinger_upper=bollinger_upper,
        bollinger_lower=bollinger_lower,
        roc_10=rate_of_change(closes),
        realized_volatility_20=realized_volatility(closes),
        swings=tuple(swings),
        structure_events=tuple(structure_events(values, swings, timeframe)),
        fair_value_gaps=tuple(fair_value_gaps(values, timeframe)),
    )

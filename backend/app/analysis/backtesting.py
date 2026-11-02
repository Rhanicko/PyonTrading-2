from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from app.analysis.professional import liquidity_sweep, opening_range, volume_momentum
from app.analysis.technical import TechnicalSnapshot, analyze_completed_candles, completed_candles
from app.schemas.market import Candle


Direction = Literal["LONG", "SHORT"]
StrategyId = Literal[
    "PRICE_STRUCTURE_BASELINE", "ICT_LIQUIDITY_REVERSAL", "MOMENTUM_CONTINUATION", "HTF_TREND_PULLBACK",
    "LIQUIDITY_SWEEP_PROXY", "VWAP_TICK_PROXY_MOMENTUM", "OPENING_RANGE_BREAKOUT",
    "VOLUME_PROFILE_PROXY_AUCTION", "ORDER_FLOW_FUTURES_CONFIRMATION",
]

TIMEFRAME = timedelta(minutes=5)
LOOKBACK_BARS = 80
HOLD_BARS = 6


@dataclass(frozen=True)
class HistoricalSignal:
    strategy_id: StrategyId
    strategy_version: str
    direction: Direction
    known_at_index: int
    source_bar_time: object
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class BacktestTrade:
    strategy_id: StrategyId
    direction: Direction
    known_at_index: int
    entry_index: int
    exit_index: int
    gross_points: float
    net_points: float | None
    spread_cost_points: float | None


@dataclass(frozen=True)
class StrategyBacktestResult:
    strategy_id: StrategyId
    strategy_version: str
    observed_signals: int
    completed_trials: int
    gross_wins: int
    gross_losses: int
    gross_points: float
    net_points: float | None
    reason_codes: tuple[str, ...]


def _direction_from_ict(snapshot: TechnicalSnapshot, candle: Candle) -> Direction | None:
    if not snapshot.structure_events:
        return None
    latest = snapshot.structure_events[-1]
    if latest.detected_at != candle.open_time_utc + TIMEFRAME:
        return None
    active_gaps = [gap for gap in snapshot.fair_value_gaps if gap.invalidated_at is None and gap.direction == latest.direction]
    if not active_gaps:
        return None
    return "LONG" if latest.direction == "BULLISH" else "SHORT"


def _direction_from_momentum(snapshot: TechnicalSnapshot, history: list[Candle]) -> Direction | None:
    if snapshot.adx_14 is None or snapshot.macd_histogram is None or len(history) < 21:
        return None
    current = history[-1]
    prior = history[-21:-1]
    if snapshot.trend_context == "EMA_BULLISH" and snapshot.adx_14 >= 20 and snapshot.macd_histogram > 0 and current.close > max(bar.high for bar in prior):
        return "LONG"
    if snapshot.trend_context == "EMA_BEARISH" and snapshot.adx_14 >= 20 and snapshot.macd_histogram < 0 and current.close < min(bar.low for bar in prior):
        return "SHORT"
    return None


def _direction_from_pullback(snapshot: TechnicalSnapshot, history: list[Candle]) -> Direction | None:
    if snapshot.ema_20 is None or snapshot.ema_60 is None or snapshot.atr_14 is None or len(history) < 2:
        return None
    current, previous = history[-1], history[-2]
    if snapshot.trend_context == "EMA_BULLISH" and current.low <= snapshot.ema_20 and current.close > snapshot.ema_20 and current.close > previous.close:
        return "LONG"
    if snapshot.trend_context == "EMA_BEARISH" and current.high >= snapshot.ema_20 and current.close < snapshot.ema_20 and current.close < previous.close:
        return "SHORT"
    return None


def _direction_from_price_baseline(snapshot: TechnicalSnapshot, history: list[Candle]) -> Direction | None:
    """Price-only breakout baseline used to measure whether proxy inputs add value."""
    if snapshot.trend_context not in {"EMA_BULLISH", "EMA_BEARISH"} or len(history) < 21:
        return None
    current, prior = history[-1], history[-21:-1]
    if snapshot.trend_context == "EMA_BULLISH" and current.close > max(bar.high for bar in prior):
        return "LONG"
    if snapshot.trend_context == "EMA_BEARISH" and current.close < min(bar.low for bar in prior):
        return "SHORT"
    return None


def _direction_from_liquidity_sweep_proxy(snapshot: TechnicalSnapshot, history: list[Candle]) -> Direction | None:
    report = liquidity_sweep(history, snapshot, point=None)
    if report.state != "TRIGGERED":
        return None
    return "LONG" if report.direction == "BULLISH" else "SHORT" if report.direction == "BEARISH" else None


def _direction_from_vwap_tick_proxy(snapshot: TechnicalSnapshot, history: list[Candle]) -> Direction | None:
    report = volume_momentum(history, snapshot)
    if report.state not in {"ARMED", "TRIGGERED"}:
        return None
    return "LONG" if report.direction == "BULLISH" else "SHORT" if report.direction == "BEARISH" else None


def _direction_from_opening_range(history: list[Candle]) -> Direction | None:
    report = opening_range(history)
    if report.state != "BREAKOUT":
        return None
    return "LONG" if report.direction == "BULLISH" else "SHORT" if report.direction == "BEARISH" else None


STRATEGY_CATALOG: tuple[tuple[StrategyId, str, str], ...] = (
    ("PRICE_STRUCTURE_BASELINE", "price-structure-baseline-v1", "PRICE_ONLY_BASELINE"),
    ("ICT_LIQUIDITY_REVERSAL", "ict-liquidity-reversal-v1", "ICT_PRICE_STRUCTURE"),
    ("MOMENTUM_CONTINUATION", "momentum-continuation-v1", "PRICE_INDICATORS_ONLY"),
    ("HTF_TREND_PULLBACK", "htf-trend-pullback-v1", "PRICE_INDICATORS_ONLY"),
    ("LIQUIDITY_SWEEP_PROXY", "liquidity-sweep-proxy-v1", "PRICE_ONLY_SWEEP_NO_ABSORPTION"),
    ("VWAP_TICK_PROXY_MOMENTUM", "vwap-tick-proxy-momentum-v1", "BROKER_TICK_PROXY"),
    ("OPENING_RANGE_BREAKOUT", "session-opening-range-v1", "COMPLETED_CANDLE_SESSION_RULE"),
    ("VOLUME_PROFILE_PROXY_AUCTION", "close-bucket-tick-proxy-profile-v1", "PROXY_NOT_TRADE_AT_PRICE"),
    ("ORDER_FLOW_FUTURES_CONFIRMATION", "licensed-futures-flow-gate-v1", "LICENSED_FUTURES_DATA_REQUIRED"),
)


def evaluate_historical_signals(candles: list[Candle]) -> list[HistoricalSignal]:
    """Evaluate independent strategies using only data known at each candle close."""
    values = completed_candles(candles)
    signals: list[HistoricalSignal] = []
    cooldown_until: dict[tuple[StrategyId, Direction], int] = {}
    evaluators = (
        ("PRICE_STRUCTURE_BASELINE", "price-structure-baseline-v1", _direction_from_price_baseline),
        ("ICT_LIQUIDITY_REVERSAL", "ict-liquidity-reversal-v1", _direction_from_ict),
        ("MOMENTUM_CONTINUATION", "momentum-continuation-v1", _direction_from_momentum),
        ("HTF_TREND_PULLBACK", "htf-trend-pullback-v1", _direction_from_pullback),
        ("LIQUIDITY_SWEEP_PROXY", "liquidity-sweep-proxy-v1", _direction_from_liquidity_sweep_proxy),
        ("VWAP_TICK_PROXY_MOMENTUM", "vwap-tick-proxy-momentum-v1", _direction_from_vwap_tick_proxy),
        ("OPENING_RANGE_BREAKOUT", "session-opening-range-v1", _direction_from_opening_range),
    )
    for index in range(LOOKBACK_BARS - 1, len(values)):
        # Each rule has a bounded 80-bar context. Recomputing the entire prior
        # dataset here would be quadratic within another scan and makes a local
        # 1,000-candle research run needlessly slow without adding evidence.
        history = values[max(0, index - LOOKBACK_BARS + 1):index + 1]
        snapshot = analyze_completed_candles(history, TIMEFRAME)
        for strategy_id, version, evaluator in evaluators:
            if strategy_id == "ICT_LIQUIDITY_REVERSAL":
                direction = evaluator(snapshot, history[-1])
            elif strategy_id == "OPENING_RANGE_BREAKOUT":
                direction = evaluator(history)
            else:
                direction = evaluator(snapshot, history)
            if direction is None or index < cooldown_until.get((strategy_id, direction), -1):
                continue
            signals.append(HistoricalSignal(
                strategy_id=strategy_id,
                strategy_version=version,
                direction=direction,
                known_at_index=index,
                source_bar_time=history[-1].open_time_utc,
                reason_codes=("COMPLETED_CANDLES_ONLY", "DECISION_TIME_REPLAY", "RESEARCH_ONLY"),
            ))
            cooldown_until[(strategy_id, direction)] = index + HOLD_BARS
    return signals


def run_backtest(candles: list[Candle], point: float | None) -> tuple[list[StrategyBacktestResult], list[BacktestTrade], tuple[str, ...]]:
    """Run a conservative close-to-next-open, fixed-horizon historical replay.

    It models only broker-recorded candle spread. Commission and fill slippage
    are deliberately *not* estimated; affected net metrics remain unavailable.
    """
    values = completed_candles(candles)
    if len(values) < LOOKBACK_BARS + HOLD_BARS + 1:
        return [], [], ("HISTORY_INSUFFICIENT", "NO_BACKTEST_PERFORMANCE_CLAIM")

    signals = evaluate_historical_signals(values)
    trades: list[BacktestTrade] = []
    for signal in signals:
        entry_index = signal.known_at_index + 1
        exit_index = entry_index + HOLD_BARS
        if exit_index >= len(values):
            continue
        entry, exit_candle = values[entry_index], values[exit_index]
        side = 1 if signal.direction == "LONG" else -1
        gross_points = side * (exit_candle.close - entry.open) / point if point else 0.0
        spread_cost_points = float(entry.spread_points) if point and entry.spread_points is not None else None
        net_points = gross_points - spread_cost_points if spread_cost_points is not None else None
        trades.append(BacktestTrade(
            strategy_id=signal.strategy_id, direction=signal.direction, known_at_index=signal.known_at_index,
            entry_index=entry_index, exit_index=exit_index, gross_points=gross_points,
            net_points=net_points, spread_cost_points=spread_cost_points,
        ))

    results: list[StrategyBacktestResult] = []
    for strategy_id, version, source_label in STRATEGY_CATALOG:
        strategy_signals = [signal for signal in signals if signal.strategy_id == strategy_id]
        strategy_trades = [trade for trade in trades if trade.strategy_id == strategy_id]
        cost_complete = bool(strategy_trades) and all(trade.net_points is not None for trade in strategy_trades)
        results.append(StrategyBacktestResult(
            strategy_id=strategy_id, strategy_version=version,
            observed_signals=len(strategy_signals), completed_trials=len(strategy_trades),
            gross_wins=sum(trade.gross_points > 0 for trade in strategy_trades),
            gross_losses=sum(trade.gross_points < 0 for trade in strategy_trades),
            gross_points=sum(trade.gross_points for trade in strategy_trades),
            net_points=sum(trade.net_points for trade in strategy_trades) if cost_complete else None,
            reason_codes=(
                "COMPLETED_CANDLES_ONLY", "NEXT_BAR_ENTRY", "FIXED_HORIZON_EXIT",
                "BROKER_SPREAD_ONLY" if cost_complete else "COSTS_INCOMPLETE",
                source_label,
                "COMMISSION_UNAVAILABLE", "NO_ORDER_EXECUTION",
            ),
        ))
    return results, trades, ("BACKTEST_RESEARCH_ONLY", "COMMISSION_UNAVAILABLE", "NO_ORDER_EXECUTION")

---
name: strategy-backtesting
description: Run chronological completed-candle backtests with no lookahead and explicit cost limitations.
---

# Strategy backtesting

Freeze features at each decision close. Enter no earlier than the following bar/open and evaluate only outcomes that exist after the decision timestamp.

- Keep strategy ID and version, input source categories, candle IDs/times, known-at time, and reason codes.
- Compare price-only baselines with proxy strategies and genuine order-flow strategies separately.
- Do not backtest a genuine futures-flow strategy unless licensed historical futures trades/depth are available.
- Include spread only when historically recorded. Keep commission, swap, slippage, latency, and fill assumptions as `UNAVAILABLE` unless sourced.
- Use chronological walk-forward partitions and report regime-specific results, drawdown, and sample counts.

Backtest results are research evidence, never a promise of future performance or a trading instruction.

# Signal rules

The live dashboard remains research-only. It may display `NO TRADE`, `WATCH LONG` or `WATCH SHORT` research context, but it does not display an entry, stop, target, volume or broker instruction.

The Backtesting Lab evaluates three versioned historical research rules independently:

- `ict-liquidity-reversal-v1`: a completed-close structural event with a same-direction unmitigated fair-value gap.
- `momentum-continuation-v1`: EMA alignment, ADX, MACD direction and a completed-close 20-bar breakout.
- `htf-trend-pullback-v1`: EMA trend context followed by a completed pullback and recovery through EMA20.

These are experimental replay rules, not approved live strategies. They use only completed candles and begin a hypothetical trial on the next bar to avoid look-ahead. A failed news, freshness, source or validation gate continues to prevent any execution interpretation.

## Live research ensemble

The live research screen has three separate, versioned deterministic readers: `structure-alignment-v1`, `momentum-alignment-v1`, and `range-breakout-v1`. They read completed M5/M15/H1/H4 broker bars and return `WATCH_LONG`, `WATCH_SHORT`, or `ABSTAIN` independently. A research watch state requires at least two readers to agree in the same direction and all data-integrity and event-risk gates to be clear.

`WATCH_*` is still only a research classification. It has no entry price, stop, target, volume, confidence percentage, order route, or automatic promotion. The ensemble outputs `NO_TRADE` whenever evidence is stale, incomplete, conflicting, quality-gated, or event-gated.


# Signal rules

The live dashboard remains research-only. It may display `NO TRADE`, `WATCH LONG` or `WATCH SHORT` research context. Only an active, source-backed watch can show unvalidated reference entry, stop, TP1 and TP2 levels; no volume or broker instruction is generated.

The Backtesting Lab evaluates three versioned historical research rules independently:

- `ict-liquidity-reversal-v1`: a completed-close structural event with a same-direction unmitigated fair-value gap.
- `momentum-continuation-v1`: EMA alignment, ADX, MACD direction and a completed-close 20-bar breakout.
- `htf-trend-pullback-v1`: EMA trend context followed by a completed pullback and recovery through EMA20.

These are experimental replay rules, not approved live strategies. They use only completed candles and begin a hypothetical trial on the next bar to avoid look-ahead. A failed news, freshness, source or validation gate continues to prevent any execution interpretation.

## Live research ensemble

The live research screen has three versioned deterministic readers: `structure-alignment-v1`, `momentum-alignment-v1`, and `range-breakout-v2`. Structure uses completed M5/M15/H1/H4 broker bars; momentum and range breakout use the same completed M5 source, so their votes are correlated rather than statistically independent. Range breakout now requires the latest completed M5 close to exceed the previous 20 completed closes in its direction. A research watch state requires at least two readers to agree in the same direction and all data-integrity and event-risk gates to be clear. Publication additionally requires completed M5/M15/H1 alignment, a separate proof, and current source checks.

`WATCH_*` is still only a research classification. When its quote is fresh and within one completed-M5 ATR of the last completed close, the dashboard may show a reference entry at the broker ask/bid and one-ATR stop, one-ATR TP1, two-ATR TP2, rounded to the broker tick size. This simple 1R/2R scenario has not been shown profitable after costs; it is not a recommended holding period, confidence percentage, order route, or automatic promotion. The ensemble outputs `NO_TRADE` whenever evidence is stale, incomplete, conflicting, quality-gated, or event-gated; then levels are absent.

## Automatic publication and history

A directional watch is published to signal history only after nine snapshot checks pass: fresh broker bid/ask, completed and aligned M5/M15/H1 structures, a new completed M5 close beyond the previous 20 completed closes in the watch direction, clear data quality, a live source-labelled USD calendar without a known elevated window, at least two agreeing deterministic rules with no opposing vote, all central research gates passing, levels tied to the same quote and completed M5 candle, and a broker spread that agrees with reported points and is no more than 25% of completed M5 ATR. The strict completed-close trigger and spread threshold are conservative, unvalidated filters, not measured win-rate improvements. Missing commission or slippage data and an incomplete public-event calendar remain limitations.

One immutable record is written per eligible broker/server, symbol, completed M5 bar, direction, and feature version. It retains the source timestamps, rule versions, proof checks, and the entry/stop/TP1/TP2 references. The browser checks for new records every five seconds and shows an in-app alert only while its current broker quote and connection remain live; desktop notifications require opt-in. The publication proof is evidence coverage, never a calibrated probability, profitability claim, order, or authorization to trade.

After 12 **contiguous, completed** M5 candles from the same broker/server, a separate append-only follow-up records the anchor and later MT5 candle closes, directional price change, and source times. Until then it remains pending; a gap or missing broker evidence is not silently bridged. The original signal and its frozen levels never change. A favorable 12-bar close is **not** a TP fill, stop result, cost-adjusted return, trade win, or probability estimate. This adapts the completed-close trigger, preplanned level, one-time alert, and later audit concepts from the [day-trader-skill reference](https://github.com/Jakeschincariol/day-trader-skill) without importing its US-stock scanners, unsupported XAUUSD feeds, or broker-order capabilities.


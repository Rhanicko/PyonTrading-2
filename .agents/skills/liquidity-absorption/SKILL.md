---
name: liquidity-absorption
description: Detect completed-candle liquidity sweeps and prevent unsupported absorption claims.
---

# Liquidity and absorption research

Record every swing level with the time it became knowable. A sweep requires a completed candle to trade beyond that confirmed level and close back through it. A reclaim or structure confirmation must also be timestamped after the level was known.

- Use `WATCH_LONG`, `WATCH_SHORT`, or `ABSTAIN`; never call a setup an entry.
- Price and broker candles can establish a sweep/reclaim only.
- Absorption, trapped participants, and aggressive-flow claims require `FUTURES_EXECUTED_FLOW`; otherwise set absorption to `UNAVAILABLE_NO_EXECUTED_FLOW`.
- Account for spread and stale quotes as gates, not as synthetic confirmation.
- Retain level, timestamps, source category, invalidation conditions, and reason codes.

On conflicts, stale source data, or a forming candle, abstain.

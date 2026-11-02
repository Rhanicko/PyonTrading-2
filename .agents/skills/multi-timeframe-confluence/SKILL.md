---
name: multi-timeframe-confluence
description: Compare independently computed PyonTrading D1, H4, H1, M15, M5 and M1 evidence without double-counting correlated indicators or overriding missing data.
---

# Multi-timeframe confluence

Compute each timeframe separately from completed source candles. State directional evidence, conflicting evidence, structural invalidation, liquidity references and source timestamp per timeframe.

Do not let M1 override higher-timeframe context automatically. Treat derived indicators from the same price move as correlated evidence, not independent votes. If a required timeframe is stale, missing or misordered, surface `UNAVAILABLE` or `CONFLICTING_EVIDENCE` rather than inventing alignment.

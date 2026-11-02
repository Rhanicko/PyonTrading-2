---
name: volume-profile-analysis
description: Build source-labelled profile research and distinguish authentic volume-at-price from an MT5 tick-activity proxy.
---

# Volume-profile analysis

First identify whether the provider supplies authentic trades mapped to price. Only that source may produce an executed volume profile, POC, value area, HVN, or LVN labelled as true volume-at-price.

- With MT5 OHLC and tick volume only, a profile may use a deterministic close-bucket tick-activity proxy.
- Label that result `BROKER_TICK_PROXY` and `CLOSE_BUCKET_PROXY_NOT_VOLUME_AT_PRICE`.
- State the value-area algorithm, coverage percentage, point/tick size, deterministic tie break, timeframe, and sample window.
- Exclude forming bars and do not project a profile into future candles.
- If point size or activity is missing, return `UNAVAILABLE`.

Profile context can support research but cannot by itself issue an order, claim absorption, or claim future performance.

---
name: market-microstructure
description: Handle broker market depth and microstructure evidence without presenting broker DOM as consolidated futures depth.
---

# Market microstructure research

For MT5 depth, subscribe only when the API and symbol support it, retrieve a bounded snapshot, release the subscription, and retain observation/provider metadata.

- Broker DOM is broker-specific and is not COMEX consolidated depth.
- Return broker depth availability separately from `FUTURES_MARKET_DEPTH` eligibility.
- Do not infer spoofing, absorption, hidden liquidity, queue position, or resting-order intent from a single snapshot.
- Use licensed futures market-depth data for authentic footprint/order-book analysis only when its contract and timestamp are retained.
- Report `UNAVAILABLE` if depth is absent, stale, unlicensed, or not persisted.

Never include execution code, order routing, or broker credentials in research output.

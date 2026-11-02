---
name: mt5-data-bridge
description: Maintain PyonTrading's read-only local MetaTrader 5 data boundary, timestamp normalization and explicit source-status behavior.
---

# MT5 data bridge

Use the locally logged-in terminal as the broker-price source. Preserve native precision for calculation and status/reason codes for every quote or candle response. Treat bar position zero as forming and exclude it from completed-candle research.

Never request, store or expose broker passwords. Never substitute reference, cached or synthetic prices for a missing MT5 quote, and never introduce an order-placement API.

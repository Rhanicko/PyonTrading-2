---
name: vwap-volume-momentum
description: Calculate completed-candle VWAP and relative participation with honest MT5 tick-activity labels.
---

# VWAP and momentum research

Use a stated VWAP basis. If weighted by MT5 tick volume, label it `TYPICAL_PRICE_WEIGHTED_BY_BROKER_TICK_ACTIVITY` and `BROKER_TICK_PROXY`.

- Compare latest activity with prior same time-of-day observations, excluding the current forming bar.
- Require enough historical same-slot observations before calling activity unusual.
- Combine VWAP position with completed-candle trend/momentum measurements such as EMA and ADX; surface disagreement.
- Never call tick activity executed volume, institutional participation, or order-flow confirmation.
- Return `OBSERVING`, `ARMED`, `TRIGGERED`, or `UNAVAILABLE` with inputs and reason codes.

The result is research context, not sizing, entry, stop, target, or execution logic.

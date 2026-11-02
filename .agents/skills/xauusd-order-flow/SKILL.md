---
name: xauusd-order-flow
description: Evaluate XAUUSD order-flow evidence without misrepresenting MT5 tick activity as futures execution.
---

# XAUUSD order-flow research

Use only timestamped inputs with retained provider identity. Classify every result as one of `BROKER_TICK_PROXY`, `ESTIMATED_DELTA`, `FUTURES_EXECUTED_FLOW`, `FUTURES_MARKET_DEPTH`, or `UNAVAILABLE`.

- MT5 tick volume is broker activity, not consolidated XAUUSD or COMEX volume.
- A price-direction weighted tick count is `ESTIMATED_DELTA`, never genuine delta or CVD.
- Require licensed executed futures trades before reporting executed delta, footprint, absorption, or aggressive buyer/seller activity.
- Require a retained depth snapshot and provider identity before reporting market depth.
- Use only completed candles for a decision. Keep the candle close time, observation time, source timestamp, and reason codes.
- If an input is missing, return `UNAVAILABLE`/`NO_TRADE`; do not infer it from price candles.

Output a short source table, direction as `WATCH_LONG`, `WATCH_SHORT`, or `ABSTAIN`, and the reasons that prevented stronger evidence. Never produce an order instruction.

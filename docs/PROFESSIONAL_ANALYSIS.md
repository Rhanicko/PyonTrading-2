# Professional research modules

This workstation is a read-only research application. It produces source-labelled observations and `NO_TRADE`/review states, never broker order instructions.

## Available with the connected MT5 terminal

| Module | Present input | Output boundary |
| --- | --- | --- |
| Liquidity sweep/reclaim | Completed broker candles and confirmed structure levels | A sweep/reclaim watch only; absorption stays unavailable. |
| VWAP and relative activity | Completed candles weighted by broker tick activity | Explicit `BROKER_TICK_PROXY`, never executed volume. |
| Estimated CVD | Price-direction classification of broker tick activity | Explicit `ESTIMATED_DELTA`, never genuine delta. |
| Profile proxy | Completed-close buckets weighted by broker tick activity | Explicit proxy, not volume-at-price or a footprint. |
| Opening range | IANA timezone session windows and completed candles | Observing/breakout research with no entry instruction. |
| Broker DOM inspection | Optional bounded MT5 depth snapshot | Broker-specific availability only, not consolidated futures depth. |

## Deliberately unavailable until an approved source is connected

- COMEX/GC executed trades, exchange delta/CVD, footprint, absorption and trade-at-price profiles.
- Consolidated futures market depth and historical order-book replay.
- Verified commissions, swap, slippage, latency and actual fill quality.
- Real-money execution, position sizing, entry, stop or target instructions.

## Audit path

The background worker reacts to completed M5 candles. It saves the exact professional-module state, source categories, strategy version and risk disposition to the local append-only strategy journal. Historical replay only evaluates data that was knowable at the completed decision candle and enters no earlier than the following bar.

When the local user requests **Analyze market**, the returned research screen is separately retained in Signal History with its delivery time, source timestamp, decision, market context, reason codes and an evidence-payload fingerprint. `NO_TRADE` and unavailable responses are retained too; this is a record of research shown, not an execution or trade ledger.

`REVIEW_REQUIRED`, `REJECTED`, `DATA_UNAVAILABLE`, and `NO_TRADE` are expected protective outcomes. They are not errors to suppress.

## Source setup and retained history

Use **Check sources** in the workstation to run an on-demand, read-only capability check. It reports the current MT5 terminal, completed M5 candles, tick-activity proxy, broker depth, calendar, optional cross-market context, and the deliberately unconfigured licensed-futures-flow boundary. It neither accepts nor retains provider credentials.

The local archive reports coverage only for the active broker server and symbol. The background collector requests up to 30,001 M5 bars when the broker retains them. It remains `COLLECTING` until it has at least 5,000 completed M5 candles spanning 90 calendar days; only then is it marked `WALK_FORWARD_READY`. That readiness marker means the local archive has enough chronological coverage to begin a separately reviewed walk-forward study. It is not a claim of profitable performance or a model promotion.

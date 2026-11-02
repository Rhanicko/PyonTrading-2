---
name: pyon-mt5-integrity
description: Verify PyonTrading's local read-only MT5 inputs, timestamp normalization, source status and volume labels.
---

# Pyon MT5 integrity

## Procedure

1. Start with `backend/app/adapters/mt5.py`, then trace through
   `market/freshness.py` and `services/live.py`.
2. Preserve raw and normalized timestamps, exact configured symbol, broker
   metadata, `DataStatus`, source and reason codes.
3. Exclude the forming bar from every derived/research decision. Treat tick
   activity as `BROKER_TICK_PROXY` only.

## Inputs and outputs

- Inputs: local MT5 quote, broker metadata and chronologically ordered candles.
- Output: source-labelled data or an explicit unavailable/stale state.

## Failure modes

Terminal unavailable, exact symbol missing, crossed/stale quote, future or
duplicate candle, missing broker precision, and insufficient completed history
must produce a conservative typed state. Never substitute another provider.

## Tests and references

Run `backend/tests/test_mt5_adapter.py`, `test_freshness.py` and
`test_timestamps.py`. See `docs/DATA_PROVENANCE.md` and `AGENTS.md`.

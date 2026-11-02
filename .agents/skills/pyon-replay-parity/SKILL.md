---
name: pyon-replay-parity
description: Check that PyonTrading completed-candle decisions are reproducible from the same archived broker inputs.
---

# Pyon replay parity

## Procedure

1. Read archived completed candles through `storage/database.py`; preserve
   broker server, symbol, timeframe and observation timestamp.
2. Freeze decision-time features and strategy versions before attaching later
   outcome labels.
3. Compare only equivalent completed-bar inputs; forming bars and later data
   are never part of the original decision.

## Inputs and outputs

- Inputs: local archive, decision evidence and fixed horizon configuration.
- Output: reproducible research labels or a clear archive/history failure.

## Failure modes

Do not call a candle touch a fill, infer intrabar execution, or compare a
different broker/symbol archive as parity evidence.

## Tests and references

Run `backend/tests/test_research_pipeline_storage.py` and
`test_research_operations.py`. See `docs/BACKTEST_METHOD.md`.

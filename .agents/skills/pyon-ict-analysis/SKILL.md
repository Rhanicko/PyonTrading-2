---
name: pyon-ict-analysis
description: Maintain deterministic completed-candle PyonTrading structure, liquidity and fair-value-gap evidence without repainting.
---

# Pyon ICT analysis

## Procedure

1. Work in `backend/app/analysis/technical.py` and retain all confirmation
   timestamps before exposing a pattern.
2. Require completed-close confirmation for BOS/CHOCH and right-side bars for
   swings. Track later invalidation separately.
3. Keep liquidity, FVG and order-block language descriptive; do not imply
   institutional flow or create a trade instruction.

## Inputs and outputs

- Inputs: exact broker completed candles and timeframe duration.
- Output: typed source/confirmation/invalidation facts or `UNAVAILABLE`.

## Failure modes

Unordered bars, a forming source bar, missing precision or insufficient history
invalidate the result. Do not infer a missing structure from an indicator.

## Tests and references

Run `backend/tests/test_technical_analysis.py` and research-service tests. See
`docs/PROFESSIONAL_ANALYSIS.md` and `AGENTS.md`.

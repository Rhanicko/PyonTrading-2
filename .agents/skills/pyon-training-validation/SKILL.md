---
name: pyon-training-validation
description: Run bounded chronological PyonTrading calibration and model-registry validation without self-promotion.
---

# Pyon training validation

## Procedure

1. Use only locally archived completed candles and split them chronologically.
2. Select settings using training data, inspect validation separately and keep
   a final holdout untouched for selection.
3. Persist strategy/data/version/reason metadata in `model_versions`; require
   manual review for every result.

## Inputs and outputs

- Inputs: source-backed archive, strategy version and point/spread history.
- Output: `REVIEW_REQUIRED`, `INSUFFICIENT_DATA` or clear cost limitations.

## Failure modes

Missing commission/slippage, thin samples, leakage, or a failed holdout never
becomes a promotion or confidence claim.

## Tests and references

Run `backend/tests/test_training.py` and `test_backtesting.py`. See
`docs/BACKTEST_METHOD.md`, `docs/ROADMAP.md` and `AGENTS.md`.

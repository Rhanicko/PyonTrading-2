---
name: pyon-risk-governor
description: Maintain the central PyonTrading research veto layer for data, spread, calendar and conflicting-rule conditions.
---

# Pyon risk governor

## Procedure

1. Use `analysis/professional.py:risk_engine` as the single post-module veto.
2. Require live quote freshness, broker contract metadata, a valid spread,
   clear data integrity and calendar risk, and no contradictory active modules.
3. Let a failure only reduce eligibility to `REJECTED` or `DATA_UNAVAILABLE`.

## Inputs and outputs

- Inputs: source-labelled quote, quality report, calendar state and independent
  module observations.
- Output: research review state and reason codes; never size, stop, target or
  broker order data.

## Failure modes

Missing cost data remains `REVIEW_REQUIRED`; elevated spread, stale inputs,
unknown news and conflict must not be bypassed by a directional module.

## Tests and references

Run `backend/tests/test_professional_analysis.py`. See `docs/RISK_POLICY.md`
and `AGENTS.md`.

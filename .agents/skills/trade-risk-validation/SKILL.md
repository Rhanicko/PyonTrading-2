---
name: trade-risk-validation
description: Apply independent research risk gates without placing or preparing live orders.
---

# Risk validation

Require all of the following before a research item can leave `REVIEW_REQUIRED`: a fresh quote, source timestamp, contract metadata, current spread, verified calendar risk, non-conflicting module evidence, and a source-backed cost model.

- Missing one required input means `DATA_UNAVAILABLE` or `REJECTED`.
- High-impact or unverified event risk blocks promotion.
- Stale data, abnormal spread, broker-session uncertainty, and model drift block promotion.
- Do not calculate or publish lot size, order entry, stop, target, or real-money execution instructions.
- Record manual-review status, kill-switch status, provenance, and reason codes.

The safe default is `NO_TRADE`.

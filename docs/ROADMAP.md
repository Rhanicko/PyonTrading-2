# PyonTrading 2 roadmap

This is an implementation status document, not a claim of profitability.

| Phase | Scope | Current state | Release gate |
| --- | --- | --- | --- |
| 0 | Local setup, no-execution boundary, source contracts | Implemented | Windows launcher and local checks pass. |
| 1 | Read-only XAUUSD MT5 workstation | Implemented, live state depends on local terminal | A connected terminal must provide a real quote and exact symbol. |
| 2 | Completed-candle structure, indicators and provenance | Implemented foundation | Golden/replay fixtures must continue to prove no look-ahead. |
| 3 | Independent deterministic ensemble and central vetoes | Implemented foundation | Watch states require live quote, clear integrity, complete MTF evidence and calendar gate. Strategy settings only reduce eligibility. |
| 4 | Calendar provenance, immutable journals and source history | Implemented foundation | Provider outages remain visible and abstain safely. |
| 5 | Multi-pair scanner and cross-market logic | Deferred | Needs exact broker symbols, currency-normalization tests and bounded performance measurements. |
| 6 | Cost-aware paper outcomes and event-driven replay | Partial | Requires source-backed commission, slippage, swap and unambiguous historical fill assumptions. |
| 7 | Training lab / champion-challenger registry | Partial | Uses chronological calibration only; requires sufficient archived data, holdout evidence and human review. |
| 8 | Optional Kronos forecasting lab | Disabled | Requires upstream license/API review, explicit model-weight approval, CPU benchmark and shadow-only validation. |
| 9 | Operational handoff and quality | In progress | Local tests, desktop/mobile browser checks, backups and docs must be recorded for each release. |

## Next permitted implementation work

1. Add golden fixtures for liquidity clusters, session highs/lows, FVG/OB
   mitigation, and deterministic strategy lifecycle transitions.
2. Build an event-driven replay only after historical bid/ask and cost inputs
   are source-backed; do not infer fills from candle touches.
3. Add multi-pair scanning only after exact broker symbols and currency-sign
   handling have their own tests.
4. Evaluate Kronos as an isolated, optional shadow experiment after a user
   explicitly approves reviewed model weights and resource use.

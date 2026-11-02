---
name: strategy-orchestrator
description: Evaluate PyonTrading ICT reversal, momentum continuation and higher-timeframe pullback strategies independently before any read-only comparison.
---

# Strategy orchestrator

Keep every strategy versioned and independently testable. A candidate must retain its decision-time evidence and progress only through explicit states: `OBSERVING`, `ARMED`, `CONFIRMED`, `ELIGIBLE`, `EXPIRED`, `INVALIDATED` or `REJECTED`.

An aggregate view may explain agreement or disagreement, but must not turn multiple correlated facts into false confidence or override a failed data, news or risk gate. No strategy is execution-capable in this project.

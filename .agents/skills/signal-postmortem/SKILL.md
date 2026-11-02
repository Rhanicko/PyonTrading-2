---
name: signal-postmortem
description: Create append-only, source-preserving research postmortems and paper-trading outcome labels.
---

# Signal postmortem

When a completed-candle research module runs, write an immutable event containing strategy ID/version, candle time, source categories, state, direction, risk disposition, and reason codes.

- Do not overwrite earlier decision-time evidence.
- Label outcomes only after the agreed future completed-candle horizon exists.
- Store the outcome label version, timestamp, cost availability, and market regime.
- Separate observed paper outcomes from live trades; this system contains no live order execution.
- Report sample count and unresolved costs before any performance summary.

If evidence is incomplete, record the missing source rather than producing a success/failure conclusion.

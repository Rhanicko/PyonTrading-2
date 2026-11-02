---
name: backtest-laboratory
description: Design reproducible PyonTrading historical experiments with chronological splits, documented fills and anti-lookahead controls.
---

# Backtest laboratory

Use only versioned historical datasets with source, timezone, symbol, timeframe and retrieval metadata. Replay information in chronological order; pattern availability starts at `known_at`, never at its source bar.

Document spread, commission, slippage, partial-fill and same-bar SL/TP assumptions. Separate training, validation and held-out data. Report unavailable metrics rather than synthetic performance, and never promote a model automatically.

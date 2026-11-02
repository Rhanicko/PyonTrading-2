---
name: ict-market-structure
description: Analyze PyonTrading broker candles for confirmed swings, completed-close structure breaks, liquidity concepts and fair value gaps without repainting or claiming institutional order flow.
---

# ICT market structure

Use only source-backed, chronologically ordered completed candles. Preserve `source_bar_time`, `confirmation_bar_time`, `known_at`, `detected_at`, and later `invalidated_at` for every pattern.

- A swing cannot be used until its configured right-side confirmation bars have closed.
- A BOS or CHOCH requires a completed close through a previously known swing level; do not use an intrabar wick as confirmation.
- Label gaps as price-structure observations, not proof of institutional activity. Record later mitigation only from completed bars.
- Return `UNAVAILABLE` when history, precision or time ordering is inadequate.
- Do not produce entry, stop, target, confidence percentage or order action.

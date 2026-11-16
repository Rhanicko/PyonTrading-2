# Bot behavior audit — 2026-11-14 PHT

Scope: local XAUUSD signal-only workstation, MetaQuotes-Demo source. This is an operational and research audit, not evidence of profitable trading or a guarantee that every feature is defect-free. No orders were placed, no live strategy was promoted, and no broker settings were changed.

## Live coordination snapshot

At 2026-11-13 18:08:04 UTC (2026-11-14 02:08:04 PHT), `/api/research` reported `LIVE`. The three deterministic votes were `STRUCTURE_ALIGNMENT: ABSTAIN`, `MOMENTUM_ALIGNMENT: ABSTAIN`, and `RANGE_BREAKOUT: ABSTAIN`, so the ensemble returned `NO_TRADE`. The live watch was `WITHHELD`, and its publication proof failed `COMPLETED_MTF_ALIGNMENT`, `RULE_AGREEMENT_NO_OPPOSITION`, `SOURCE_BACKED_LEVELS`, and `COMPLETED_CLOSE_TRIGGER`. No entry, stop, or target may be represented as a current signal under those conditions.

| Bot | Observed state | Contribution and limitation |
| --- | --- | --- |
| Data quality sentinel | OBSERVING / LIVE | Checks tick freshness, completed-candle continuity, spread and broker clock; clear at snapshot. |
| Chart analyst | OBSERVING / LIVE | Reads completed M5, M15, H1, H4 candles; mixed cross-timeframe structure. |
| Momentum analyst | OBSERVING / LIVE | Measures completed-candle EMA, RSI, MACD, ADX, ATR; disagreement causes abstention. |
| Macro and event watcher | WATCHING / LIVE | Source-labelled USD calendar; next low-impact event outside the elevated window. Calendar absence is not a guarantee. |
| Cross-market context | OBSERVING / NOT_CONFIGURED | Exact broker symbols for DXY, yield, oil and volatility are not configured; no external context is invented. |
| Liquidity reversal analyst | OBSERVING / LIVE | Completed-candle sweep/reclaim proxy; cannot claim futures absorption. |
| Volume and auction analyst | OBSERVING / LIVE | MT5 tick-activity VWAP/profile proxies, not executed exchange volume. |
| Order-flow analyst | BLOCKED / LIVE source | Genuine executed futures flow/depth unavailable; estimated delta stays separate. |
| Independent risk manager | COLLECTING_EVIDENCE / LIVE | Can reject incomplete/conflicting research; cannot approve an order. |
| Strategy research and postmortem | COLLECTING_EVIDENCE / LIVE | Freezes candidates and later labels outcomes; no self-promotion. |
| Strategy ensemble and abstention | COLLECTING_EVIDENCE / LIVE | Three versioned rules vote; two agreeing votes are required before a watch, followed by separate publication proof. |

The shared path is: MT5 quote and completed candles + calendar -> quality and feature readers -> three independent strategy votes -> event and risk gates -> live watch -> source-backed level and completed-close proof -> optional automatic signal history. The background pipeline was `RUNNING` at inspection and completed new jobs; focused tests covered a fixture where eligible evidence is actually recorded as an automatic signal. All 108 backend tests passed on this audit, with one dependency deprecation warning. This does not prove uninterrupted live operation.

## History, coverage, and validation

- The database held 31,497 completed M5 candles (2026-05-17 through 2026-11-13), while scheduled calibration intentionally reads the latest 6,000. An additional **read-only** offline calibration used all 31,497 candles and the broker's 0.01 point size. This did not change live rules.
- Across six candle-only candidates, **none had positive spread-adjusted points in both chronological validation and held-out partitions**. Results in points, not dollars: price structure +10,833 / -14,091; ICT liquidity reversal -9,530 / -1,940; momentum continuation -9,055 / -12,610; M5 trend pullback -940 / +14,468; liquidity sweep proxy -9,088 / +2,761; opening-range breakout -18,533 / -23,626 (validation / held-out). Three source-dependent candidates had insufficient data. Commission, slippage, swap and realistic fill uncertainty are absent. These numbers cannot establish profitability.
- Live validation showed 303 frozen decisions, 27 labelled candidates, 18 directional matches overall, but only 1 of 6 held-out labels matched. The system correctly reports `INSUFFICIENT_LABELS`, `COSTS_INCOMPLETE`, and no accuracy percentage. Signal history contained 23 records: 0 automatic publications and 4 directional on-demand watches, which are not validated trade instructions.
- There were no research jobs from 2026-11-13 13:25 to 17:50 UTC even though the app process was up. M5 candles for the intervening hours were backfilled together at 17:57 UTC. The records show a source/research coverage interruption, **not its cause**. A current `RUNNING` status alone does not prove continuous historical coverage.
- Job history at inspection: 326 completed, 1 failed and 3 invalidated; the failed/invalidated jobs were older, not current. The current `WITHHELD` outcome is consistent with mixed structure and no completed-close breakout, not evidence that the publication path is impossible.

## Decisions and next evidence

No live threshold was loosened and no model was promoted. The longer data window did not pass validation. Next priorities are: (1) diagnose and surface source/research coverage gaps, (2) configure only verifiable cross-market sources, (3) obtain legitimate executed-flow data if that bot is needed, (4) collect many more independent, cost-complete outcome labels, and (5) replay candidate rule changes chronologically before separate manual promotion. More frequent or less strict alerts would not by itself make the signals more accurate.

The offline calibration is not a full live-pipeline replay, and focused unit/integration tests do not prove future live performance. Multiple-rule selection can overfit historical market data; see [Sullivan, Timmermann and White](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00163) and [Bailey et al.](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

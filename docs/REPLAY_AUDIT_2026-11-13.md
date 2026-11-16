# XAUUSD replay audit — 2026-11-13

This is a local research check, not evidence of profitable live signals. The source is 6,000 archived completed M5 candles from `MetaQuotes-Demo` for `XAUUSD`, from 2026-09-29 15:35 UTC through 2026-11-13 12:25 UTC. The broker-reported point size at the check was `0.01`. The corrected backtest was also run through the live application and saved as run `04fda1cf11904f53a657a24727bcc513`.

| M5 replay rule | Completed trials | Spread-adjusted points, not net P&L |
| --- | ---: | ---: |
| Price breakout baseline | 245 | -11,919 |
| ICT liquidity reversal | 416 | +1,901 |
| Momentum continuation | 165 | -9,628 |
| M5 trend pullback | 339 | +18,097 |
| Liquidity-sweep proxy | 170 | +14,538 |
| Opening-range breakout | 333 | -21,337 |

The VWAP tick proxy, volume-profile proxy, and licensed futures-flow rows each produced zero completed trials. Do not substitute a proxy row for actual executed order flow.

The separate holding-horizon calibration used chronological 60/20/20 partitions. Five of six active strategies had *negative spread-adjusted validation points* after a horizon was selected on training data. Only opening range was positive on validation, while its training score was negative. These mixed results do not support promoting any rule or assigning a calibrated confidence probability. The later held-out scores are exploratory and were not used to pick a horizon.

The audit found and corrected three replay validity problems: a six-bar exit previously used the seventh bar's close; some outcomes crossed chronological partition boundaries; and trials crossed missing M5 intervals. The current replay uses the sixth held bar's close, excludes trials crossing training/validation boundaries from those partitions, and excludes any holding window that spans an archive gap.

The live signal provider is a different multi-timeframe, quote, calendar, and risk-gated path; these M5 strategy rows are **not** a historical replay of its publication decisions. The controlled pipeline integration test publishes one frozen eligible signal, but the live history checked during this audit contained no automatic published signals. At the check, the live watch was withheld during a high-impact USD event window without directional rule agreement. No gate was relaxed to force a signal.

Recorded entry-bar spread is the only modeled cost. Commission, slippage, swaps, stop/target ordering, tick-level fills, and broker portability remain unverified. No orders were placed or simulated. Before claiming higher signal accuracy, collect more frozen natural live decisions and their later outcomes, replay the *complete* historical publication path with source-time calendar/quotes, and evaluate across multiple regimes and brokers with complete costs.

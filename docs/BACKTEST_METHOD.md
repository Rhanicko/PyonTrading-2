# Backtest method

The local Backtesting Lab is a bounded M5 historical research replay. It prefers up to 6,000 archived completed M5 candles from the active broker server and symbol; only when that archive is absent does it request the same bounded history directly from MT5. It excludes the forming candle.

## Current deterministic replay

- The lab compares a price-only breakout baseline, ICT liquidity reversal, momentum continuation, M5 trend pullback, a completed-candle liquidity-sweep proxy, VWAP/tick-activity momentum and opening-range breakout. The M5 pullback row does not replay higher-timeframe confirmation.
- Close-bucket volume-profile auction and licensed-futures-flow confirmation are included as explicit comparison rows, but produce zero trials until their authentic required data is connected. This prevents a proxy result from being presented as genuine order-flow performance.
- A signal becomes available only at the close of its completed decision candle. A hypothetical trial begins at the next bar open and ends after six completed M5 bars.
- Trials spanning missing M5 candle intervals are excluded and flagged; the replay does not treat a weekend, session break, or archive gap as an uninterrupted six-bar holding period.
- Duplicate same-direction observations for a strategy use a six-bar cooldown.
- The replay retains its source timeframe, active-broker archive/fallback provenance, candle coverage, source timestamp and immutable run identifier locally.

## Cost and validity boundary

- When MT5 provides both symbol point size and entry-bar spread points, the result subtracts that recorded spread only.
- Commission, slippage, swaps, partial fills, stop/target ordering and tick-level fills are unavailable in the current data bridge. Net results remain unavailable when recorded spread or point metadata is absent.
- Even when spread is available, the run carries `COMMISSION_UNAVAILABLE` and is not a validated performance claim.
- The backtest does not place, simulate placing, or authorize broker orders.
- The current local replay is M5 candle based. It does not claim M1/tick replay, trade-at-price replay, historical depth replay, actual fills, or cross-broker portability.
- Holding-horizon calibration uses chronological 60/20/20 partitions. A trial belongs to training or validation only if its outcome is known before that partition ends; trials spanning a boundary are not used for either partition's metrics. Calibration remains review-only and does not promote a strategy or establish a probability.
- The lab's standalone M5 strategy rows are not a historical replay of the complete live multi-timeframe, quote, event, and risk-gated signal publication path. Do not infer live signal accuracy from these rows.

## Frozen paper-candidate validation

The background pipeline also records an immutable evidence snapshot only when a completed M5 review is processed. A `WATCH_LONG` or `WATCH_SHORT` research state may become a paper candidate if the local paper kill switch is off. Each record retains the exact completed-candle feature payload, strategy versions, source states, event-risk context, quote bid/ask/spread, and explicit null values for unavailable commission, slippage, swap and actual fill quality.

After 12 later completed M5 bars are archived from the same broker-server series, the system records only the observed price-direction outcome. It does not convert the label into an executed-fill result or a performance guarantee. `/api/research/validation` reports chronological 60/20/20 label counts and regime counts, but keeps accuracy unavailable until at least 30 labelled paper candidates exist. Even then it remains `REVIEW_REQUIRED`, with no automatic promotion.

## Signal-proof audit

The Validation screen also audits up to the 500 most recent stored research runs for the configured symbol. It counts only runs with non-empty, frozen decision-time publication checks, shows each failed check's frequency, and separately reports all-time automatically published research signals. Older runs without proof checks are included in the sample count but not misclassified as checked. Legacy research runs are symbol-scoped rather than broker-verified; sample counts and all-time publication counts have different scopes.

This audit explains why a research watch was withheld. It does not replay the full live publication path, establish a profitable edge, infer fills, or loosen any publication gate. The existing fixed-horizon directional labels remain separate from net performance, which is unavailable without source-backed complete costs.

## On-demand full-archive hold-out validation

`POST /api/backtests/validate` reads up to 50,000 archived completed M5 candles from the exact active broker server and symbol, including when the quote reports `MARKET_CLOSED`. It does not borrow another broker's archive. It runs the existing 60/20/20 calibration without persisting a model, changing strategy settings, or publishing a signal. The Validation screen displays validation and held-out trial counts and recorded-spread-adjusted points separately; missing point or spread data remains unavailable.

This is one chronological train/validation/held-out split, not rolling walk-forward validation. The first request computes the archive result. Later requests in the same process reuse it only while the immutable completed-candle archive, broker identity, symbol, and point value are unchanged; the response labels a cache hit and refreshes the current quote status. A new completed bar invalidates the cache.

This is still a standalone M5 strategy comparison, not full multi-timeframe live-signal replay. Commission, slippage, swap, tick-level fills, calendar-at-decision history, and historical bid/ask execution are unavailable, so the result is not net profit or a basis for automatic model promotion.


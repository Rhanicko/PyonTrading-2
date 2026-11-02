# Backtest method

The local Backtesting Lab is a bounded M5 historical research replay. It prefers up to 6,000 archived completed M5 candles from the active broker server and symbol; only when that archive is absent does it request the same bounded history directly from MT5. It excludes the forming candle.

## Current deterministic replay

- The lab compares a price-only breakout baseline, ICT liquidity reversal, momentum continuation, higher-timeframe trend pullback, a completed-candle liquidity-sweep proxy, VWAP/tick-activity momentum and opening-range breakout.
- Close-bucket volume-profile auction and licensed-futures-flow confirmation are included as explicit comparison rows, but produce zero trials until their authentic required data is connected. This prevents a proxy result from being presented as genuine order-flow performance.
- A signal becomes available only at the close of its completed decision candle. A hypothetical trial begins at the next bar open and ends after six completed M5 bars.
- Duplicate same-direction observations for a strategy use a six-bar cooldown.
- The replay retains its source timeframe, active-broker archive/fallback provenance, candle coverage, source timestamp and immutable run identifier locally.

## Cost and validity boundary

- When MT5 provides both symbol point size and entry-bar spread points, the result subtracts that recorded spread only.
- Commission, slippage, swaps, partial fills, stop/target ordering and tick-level fills are unavailable in the current data bridge. Net results remain unavailable when recorded spread or point metadata is absent.
- Even when spread is available, the run carries `COMMISSION_UNAVAILABLE` and is not a validated performance claim.
- The backtest does not place, simulate placing, or authorize broker orders.
- The current local replay is M5 candle based. It does not claim M1/tick replay, trade-at-price replay, historical depth replay, actual fills, or cross-broker portability.

## Frozen paper-candidate validation

The background pipeline also records an immutable evidence snapshot only when a completed M5 review is processed. A `WATCH_LONG` or `WATCH_SHORT` research state may become a paper candidate if the local paper kill switch is off. Each record retains the exact completed-candle feature payload, strategy versions, source states, event-risk context, quote bid/ask/spread, and explicit null values for unavailable commission, slippage, swap and actual fill quality.

After 12 later completed M5 bars are archived from the same broker-server series, the system records only the observed price-direction outcome. It does not convert the label into an executed-fill result or a performance guarantee. `/api/research/validation` reports chronological 60/20/20 label counts and regime counts, but keeps accuracy unavailable until at least 30 labelled paper candidates exist. Even then it remains `REVIEW_REQUIRED`, with no automatic promotion.


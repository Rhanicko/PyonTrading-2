# Data provenance and freshness

MT5 connected to the user's broker is the only authoritative broker-price source. Each quote response contains provider (`MT5`), broker tick time in UTC, local observation time in UTC, symbol, bid/ask, derived spread, native precision metadata and a data-status/reason-code pair. The UI rounds only display values to two decimals.

The quote classifier marks ticks LIVE through 5 seconds, DELAYED through 15 seconds, then STALE; both thresholds are environment-configurable. Missing terminal/package and unknown symbols produce an explicit unavailable state. No other quote feed is used as fallback.

A broker tick or forming-bar open time more than 60 seconds in the future relative to the local UTC clock is normally `SOURCE_ERROR`, never `LIVE`. The only exception is a verifiable, whole-hour broker-server offset (one to fourteen hours, within two minutes of an exact hour) confirmed from the current tick. In that case, the application retains raw MT5 time, offset seconds and the `BROKER_CLOCK_OFFSET_NORMALIZED_*` reason while using the normalized effective UTC time. Arbitrary future timestamps remain blocked. [MQL5 Python time convention](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrom_py)

For candles, MT5 position zero is treated as the forming bar. The last chronological bar returned by `copy_rates_from_pos` is marked `completed=false`; prior bars are completed. Phase 1 makes no strategy calculation from candle data.

The background research pipeline saves only those completed bars. Its immutable identity is source, broker server, symbol, timeframe and open time, so a duplicate observation cannot overwrite the first stored raw bar and a different broker server is not silently mixed into the active archive. Each queued review retains its triggering completed M5 open time, source statuses, versioned response payload and reason codes. Calendar snapshots retain the provider URL, provider timestamp, status, reasons and complete response payload used in that review.

Outcome labels are delayed: a 12-bar M5 direction label is written only when both the anchor close and the later twelfth completed M5 close are present in the same broker-server archive. The label is an observed past outcome, not an instruction or a prediction.

## Research provenance additions

The data-quality sentinel returns its observable quote age, current and recent-spread context, completed-candle gap count, raw/effective broker-clock status and broker-session observation. A status of `WATCH` or `BLOCK` vetoes the research ensemble; it is not converted into a confidence discount.

The official macro adapter records an official provider name, source URL, local retrieval time, status, and only a machine-verifiable upcoming BLS schedule timestamp when available. BLS, BEA and Federal Reserve schedule pages do **not** become sources of forecast, previous or actual values. Any values displayed from the configured weekly public calendar retain that provider label and are independently treated as informational.

Cross-market values are read only for exact, user-configured symbols through the same connected MT5 terminal. Missing mappings stay `NOT_CONFIGURED`; no alias is guessed and no third-party price is substituted. DXY, yield, oil and volatility values are contextual features, not a causality claim.

On each background completed-M5 review, the system freezes the feature payload, SHA-256 input fingerprint, data/event state, deterministic-rule versions, exact broker quote fields and known cost availability. Commission, slippage, swaps and tick-level observed fills are stored as unavailable unless a future source-backed integration supplies them.

## Volume, order-flow and depth classification

Every professional-research output carries a source category. `BROKER_TICK_PROXY` means MT5 broker tick activity only. `ESTIMATED_DELTA` means that activity has been classified from completed-bar price direction; it is not executed buyer/seller volume or genuine CVD. `FUTURES_EXECUTED_FLOW` and `FUTURES_MARKET_DEPTH` are reserved for a configured, licensed provider that retains its contract, timestamp and raw source identity. Until such a provider is connected, genuine-flow modules remain `UNAVAILABLE`.

The local profile assigns broker tick activity to a completed bar's close bucket solely as a transparent visualization/research proxy. It is marked `CLOSE_BUCKET_PROXY_NOT_VOLUME_AT_PRICE`; POC, value area and nodes from that calculation are not exchange volume-at-price claims.

MT5 market depth, when a broker offers it, is fetched by bounded subscription and then released. It is reported as broker-specific DOM and is never relabelled as consolidated COMEX/futures market depth. No depth snapshot is converted into a spoofing, hidden-liquidity or absorption claim.


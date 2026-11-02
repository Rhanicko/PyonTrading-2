# Advanced upgrade audit — Stage 1–4 research foundation

Audited 2026-10-22 against the local FastAPI, React/Vite, SQLite and MT5-adapter application.

## Current architecture

- `MT5Adapter` is the only broker-price boundary. It reads terminal metadata, ticks and candles; it has no order-placement method.
- `LiveService` owns bounded local polling and WebSocket updates. REST remains the recovery path.
- The React dashboard consumes typed REST/WebSocket payloads from the local FastAPI process.
- SQLite/WAL stores local settings, immutable data-only observations, completed broker candles, calendar snapshots, research jobs/runs, delayed labels and calibration records.
- Calendar context comes from the configured public weekly export and is explicitly marked unverified when unavailable.

## Existing / added / deferred

| Area | Status | Evidence |
| --- | --- | --- |
| Read-only broker quote and candles | Existing | `MT5Adapter`; current quote/candle status and timestamps are returned to the UI. |
| Forming-candle exclusion | Existing and retained | MT5's final bar is marked `completed=false`. |
| Live dashboard refresh | Existing | WebSocket plus 15-second REST recovery. |
| 12-hour M5 research window | Existing | 144 completed M5 candles are required. |
| Confirmed swings, BOS/CHOCH, FVG, EMA/RSI/ATR | Added | Pure-Python `app.analysis.technical`, visible as chart-bot evidence. |
| No-lookahead unit coverage | Added | Confirmation timestamps and forming-candle exclusion tests. |
| Data-quality sentinel | Added | Tick freshness, candle-gap, spread-anomaly, broker-clock and session-transition observations gate the ensemble. |
| Official macro schedule provenance | Added | BLS iCalendar plus BEA/Federal Reserve schedule-page health, URLs and retrieval timestamps; no fabricated release values. |
| Optional cross-market context | Added | DXY, US10Y, WTI and volatility require explicit MT5 symbols; values are labelled context-only. |
| Versioned structure/momentum/range ensemble | Added, research-only | Three completed-candle deterministic votes require agreement and preserve abstention. |
| Frozen paper candidates and delayed labels | Added | Decision-time payload, quote/spread and missing-cost state are immutable; outcome labels wait for twelve future M5 bars. |
| Audit, controls, validation endpoint | Added | Local paper kill switch requires a server-side operator token; no execution capability exists. |
| Trade-entry strategies, risk sizing, broker fill simulation | Deferred | No setup may be represented as an approved order; commission/slippage/swap/fill data is not source-backed. |
| Durable completed-bar research pipeline | Added | `ResearchPipeline` archives M5/M15/H1/H4 completed bars, persists calendar snapshots and processes restart-safe research jobs without a browser request. |
| Delayed outcome labelling | Added | A label is stored only after the twelfth later completed M5 close exists in the same broker-server archive. |
| Chronological calibration | Added, review-only | `app.analysis.training` consumes only locally archived completed M5 history; calibration stays `REVIEW_REQUIRED` and never auto-promotes. |
| Source-labelled volume and order-flow research | Added, proxy-safe | Broker tick activity, estimated delta and close-bucket profile outputs carry explicit source categories; they never claim COMEX executed flow. |
| Liquidity sweep and opening-range modules | Added, research-only | Confirmed swing/reclaim timestamps and IANA session windows operate from completed candles only. |
| Broker-depth inspection | Added, bounded availability check | MT5 DOM is subscribed, read and released only when available; it is retained as broker-specific and is never labelled consolidated futures depth. |
| Independent risk review | Added, veto-only | Quote freshness, contract metadata, spread and calendar gates can only yield `REVIEW_REQUIRED`, `REJECTED` or `DATA_UNAVAILABLE`; no order fields are emitted. |
| Append-only strategy journal | Added | Each background completed-M5 review freezes module state, source labels and risk disposition without rewriting prior evidence. |
| Historical price/proxy comparison | Added, limited | The Backtesting Lab lists price-only, tick-proxy and futures-data-required strategies separately; unavailable genuine-flow variants receive zero trials. |
| Full cost-aware backtesting, walk-forward promotion, ML research | Deferred | Requires broker commission data, substantially more source-backed history, evaluation thresholds and human model approval. |
| Real-money execution | Intentionally absent | No broker order API is introduced. |

## Dependency decision

No new runtime package is installed in this stage. The analysis foundation uses the already-installed Python runtime so the desktop launcher remains simple.

- [TA-Lib](https://github.com/TA-Lib/ta-lib-python) is mature and BSD-2-Clause, but its native build/wheel considerations are not justified while the required indicators have small deterministic implementations.
- [smart-money-concepts](https://github.com/joshyattridge/smart-money-concepts) is a useful MIT-licensed reference for terminology, but its outputs are not adopted as a black box; this project retains explicit confirmation timestamps and its own tests.
- [VectorBT](https://github.com/polakowo/vectorbt) is suitable for a later isolated research laboratory, but its repository states an Apache-2.0-with-Commons-Clause license and optional dependency surface, so it is not a default local workstation dependency.
- [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) is an event-driven Rust-native engine under LGPL-3.0 and has a much broader live-execution scope. It is not appropriate for this read-only application runtime.
- [TradingAgents](https://github.com/TauricResearch/TradingAgents) is an AI research framework. It is deferred until source provenance, model cost and reproducible evaluation requirements are designed.
- [Agent Claude Trading Skills](https://github.com/dr-pabs/Agent-claude-trading-skills) was inspected directly for discipline, drawdown, backtest, postmortem, memory, news and performance-review workflows. Its own README says it is not an automated signal service. This project adapts its evidence-first and human-review principles rather than copying its stock-specific procedures.

## Technical-analysis contract

All calculations accept only completed candles and retain the following timing semantics:

- `source_bar_time`: origin pivot or first FVG bar.
- `confirmation_bar_time`: completed bar that supplied the last required confirmation input.
- `known_at` / `detected_at`: close time of the confirmation or break bar.
- `invalidated_at`: a later completed bar only; `null` when not observed.

These features are descriptive evidence, not an entry, stop, target, confidence score or execution instruction.

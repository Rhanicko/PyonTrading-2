# Architecture — Phase 1

One local FastAPI/Uvicorn process owns the browser API and serves `frontend/dist`. `LiveService` polls the isolated read-only `MT5Adapter` at a bounded configurable interval and sends timestamped quote events through `/ws/live`. REST remains the snapshot/recovery path.

`ResearchPipeline` is started with the application and is not triggered by a browser request. Its bounded responsibilities are: source collection archives only completed M5/M15/H1/H4 broker candles; a data-quality sentinel checks tick freshness, gaps, spread anomalies and retained broker-clock data; chart and momentum researchers produce completed-bar measurements; macro research refreshes the public calendar and official BLS/BEA/Federal Reserve schedule provenance; and the strategy ensemble freezes a versioned decision-time evidence bundle. Incomplete jobs recover to `QUEUED` on restart. A completed M5 bar creates a unique `RESEARCH_SNAPSHOT` job, so refreshes and repeated polls cannot create duplicate work.

`api/routes.py` validates route input and returns typed Pydantic models. `adapters/mt5.py` is the only broker-price boundary. It calls terminal initialization, metadata, tick and candle APIs only; it has no order-placement function. `adapters/official_macro.py` reads only the published BLS iCalendar and BEA/Federal Reserve schedule pages with bounded timeouts. `storage/database.py` initializes WAL SQLite tables for settings, immutable raw candles, calendar snapshots, research jobs/runs, frozen decision inputs, delayed labels, controls and audit records. The browser receives values through `/api/*` and does not talk to the MT5 terminal directly. `/api/research/pipeline` reports worker-process and persisted-record status; `/api/research/validation` reports label coverage; `/api/research/operations` reports controls and alerts.

`POST /api/research/operations/kill-switch` is local-control infrastructure only. It requires `PYON_OPERATOR_TOKEN` to be configured server-side and an exact `X-Pyon-Operator-Token` request header. It stops new paper-candidate recording; it cannot place, cancel, or modify a broker order because the application contains no such capability.

On reconnect the frontend calls REST endpoints again. WebSocket messages include type, sequence and observed UTC time; the frontend applies quote messages only after the fresh snapshot path is available.

## Module map

- `app/adapters/mt5.py`: isolated read-only MT5 terminal, quote, metadata,
  candle and broker-depth capability boundary. It contains no order method.
- `app/market/`: timestamp normalization, freshness and timeframe semantics.
- `app/analysis/`: deterministic completed-candle indicators, structure,
  quality/regime, proxy-labelled volume research, backtesting and calibration.
- `app/services/research.py`: independent chart, quality, momentum, calendar,
  context and professional research readers; it combines only eligible
  evidence and preserves abstention.
- `app/services/pipeline.py`: bounded background archive and completed-M5
  research cycle. Browser requests are not required for its work.
- `app/storage/database.py`: SQLite/WAL and forward-only migrations for source
  data, immutable journals, local strategy configuration, labels and registry.
- `app/api/routes.py`: local typed API routes. Strategy configuration and the
  paper kill switch require the configured local operator token.
- `frontend/src/`: typed REST/WebSocket dashboard, source-status displays,
  chart overlays and research-only controls.

## Current dependency baseline

Python dependencies are pinned in `backend/requirements.txt`; frontend runtime
versions are locked in `frontend/package-lock.json`. Optional forecasting and
licensed futures data are intentionally excluded from startup. See
[`TOOLING.md`](TOOLING.md) for purpose and removal constraints.


# PyonTrading 2

PyonTrading 2 is a local, read-only XAUUSD market-data workstation for a **locally installed and already logged-in MetaTrader 5 terminal**. It is a new independent application: it has no broker-order code and does not request broker passwords.

## Current scope

- Starts a configured or conventionally installed MT5 terminal once when PyonTrading starts, then reports a clear disconnected state if MT5 is absent, still starting, or later closed.
- Uses only MT5 broker bid/ask, symbol metadata and candle data for broker pricing. It never replaces a missing broker quote with a reference or synthetic price.
- Marks the latest MT5 candle as **FORMING** and keeps prior candles as completed. Displayed prices use two decimals; the API preserves broker precision.
- Serves a React dashboard from the single local FastAPI process at `http://127.0.0.1:8765` with REST snapshots and a bounded WebSocket quote poller.
- Creates a local SQLite database in WAL mode for non-sensitive settings plus immutable, completed broker-candle and research evidence records.
- Includes completed-candle technical context: confirmed swings, completed-close BOS/CHOCH events, three-candle fair value gaps, EMA, RSI and ATR. Each pattern retains confirmation timing so it cannot appear before it could have been known.
- Runs a background research pipeline independently of the browser. It archives completed M5/M15/H1/H4 bars, queues a cross-bot review on a new completed M5 bar, persists the exact public-calendar response used, and creates outcome labels only after later completed M5 bars exist.
- Runs a bounded chronological strategy calibration only when the broker exposes at least 5,000 completed M5 bars. Every calibration remains `REVIEW_REQUIRED`; it is never automatically promoted into an execution model.
- Runs source-labelled research bots for broker data quality, multi-timeframe structure, momentum, public/official macro schedules, optional cross-market context, and a versioned deterministic-rule ensemble. Each bot can abstain independently.
- Adds professional completed-candle research for liquidity sweeps/reclaims, IANA-session opening ranges, VWAP/relative tick activity, estimated delta and a close-bucket profile proxy. Each result identifies whether it is broker tick activity, an estimate, genuine futures data, or unavailable.
- Persists append-only professional strategy-module observations with their source labels and risk-review disposition after a completed M5 pipeline run.
- Checks tick freshness, completed-candle gaps, spread anomalies, retained broker-clock normalization, and observed broker-session state transitions before a research watch condition can pass.
- Reads official release schedules from BLS, BEA and the Federal Reserve with source URLs and retrieval timestamps. Official schedule availability is not represented as official forecast/actual data; the configured public calendar remains separately labelled.
- Freezes completed-candle decision inputs, rule versions, source state, spread and known missing cost fields in SQLite. Hypothetical paper candidates are outcome-labelled only after 12 later completed M5 bars exist.
- Exposes chronological validation counts, held-out-label counts, local audit events, and a token-protected paper-candidate kill switch. Model promotion remains manual and research-only.
- Includes an on-demand **Check sources** workflow that reports the active MT5/candle/calendar/context capabilities plus broker-scoped historical archive coverage. It never accepts provider credentials and explicitly shows licensed futures order flow as unavailable until a separately audited provider adapter is configured.
- Withholds hypothetical paper candidates unless commission and slippage inputs are source-backed; a directional watch alone cannot become a paper result.
- Keeps an append-only local **Signal History** of every research screen returned after **Analyze market**, including `NO_TRADE` and unavailable outcomes, their source timestamp, reason codes, and an evidence fingerprint. It is an audit trail of research provided—not a trade ledger or execution log.

Not implemented yet: a licensed COMEX/futures executed-flow and consolidated-depth provider, authentic volume-at-price/footprint data, verified broker commission/slippage/swap capture, tick-level observed fill-quality measurement, complete multi-provider calendar/news verification, structural entry/stop/target candidates, position sizing, drift thresholds, human-reviewed promotion acceptance thresholds, a multi-pair screener, full event-driven bid/ask replay, and real machine-learning/Kronos model training. A local calibration or historical replay is not a performance guarantee or high-confidence signal. Real-money order execution is intentionally absent.

## Recent research-control additions

- Local owner-controlled enablement for the three deterministic research votes,
  scoped to the exact configured broker symbol. Changes require the existing
  local operator token and apply only to future research.
- A central research veto consumes quote freshness, broker contract metadata,
  data-integrity/spread state, calendar risk and strategy conflicts. It can
  only reduce eligibility; it cannot create an order, trade level or size.
- Typed local API endpoints now cover exact symbols, calendar, worker/jobs,
  model registry, strategy configuration, and explicitly disabled Kronos
  status/forecasts.

## Prerequisites

1. Windows 10/11 x64.
2. Python **3.11 or 3.12 x64** installed from python.org and available as `python` in a new PowerShell window. The pinned MT5 wheel is Windows x64 compatible with both versions.
3. Node.js and npm for the first frontend build.
4. MetaTrader 5 desktop terminal installed and logged in to the intended account at least once. PyonTrading starts it once on application startup using MT5's saved session; no password is entered into this application.

## First run

Open ordinary PowerShell in this folder. This project deliberately does not bypass your PowerShell execution policy.

```powershell
.\scripts\environment-report.ps1
.\setup.ps1
.\Start-PyonTrading2.ps1
```

The launcher opens `http://127.0.0.1:8765`. If your PowerShell policy blocks local scripts, use the policy your organization permits, or use the direct Command Prompt alternatives below; neither route bypasses the policy:

```bat
setup.bat
Start-PyonTrading2.bat
```

## Daily desktop launch

After the first setup, double-click **PyonTrading 2** on your Windows Desktop. It starts the local workstation in the background when needed, starts MT5 once if it is not already running, waits for the workstation to become ready, then opens the dashboard. If the workstation is already running, it only opens the dashboard. Closing MT5 later disconnects the feed; the running workstation does not relaunch it.

On first connection, add your broker's exact gold symbol to MT5 Market Watch, then select the discovered alias in the dashboard. The app will not guess `XAUUSD`, `XAUUSDm`, or `GOLD`.

For optional DXY, Treasury-yield, oil, or volatility context, use **Context setup** in the dashboard and enter the corresponding exact broker symbol only after it is available from that broker. The app validates the exact symbol, adds it to MT5 Market Watch when needed, persists it locally, and refreshes the read-only context service without a restart. Startup environment values remain optional defaults only. These features are explicitly contextual, never causal proof or an execution trigger. To operate the local paper kill switch, set a strong `PYON_OPERATOR_TOKEN`; the API rejects control changes when that token is not configured.

## Development and checks

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check app tests
Pop-Location

Push-Location frontend
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
Pop-Location
```

For development UI work, use `npm.cmd run dev` in `frontend`; daily use always goes through `Start-PyonTrading2.ps1` so FastAPI serves the built files.

## Data status meanings

`LIVE`, `DELAYED`, `STALE`, `DISCONNECTED`, `MARKET_CLOSED`, `NOT_CONFIGURED`, `HISTORY_INSUFFICIENT`, and `SOURCE_ERROR` are explicit API and UI states. A stale or unavailable quote never becomes a signal. The current Phase 1 decision remains `DATA UNAVAILABLE` or `NO TRADE`; it does not recommend an order.

## Privacy and safety

- Binds only to `127.0.0.1`.
- `.env`, the local database, logs, generated assets and dependencies are ignored by Git.
- The application does not contain an MT5 trade placement call.
- A connected MT5 account mode is shown as Demo/Live/Unknown without displaying the account number.

See [architecture](docs/ARCHITECTURE.md), [professional analysis](docs/PROFESSIONAL_ANALYSIS.md), [data provenance](docs/DATA_PROVENANCE.md), [risk policy](docs/RISK_POLICY.md), and [troubleshooting](docs/TROUBLESHOOTING.md).


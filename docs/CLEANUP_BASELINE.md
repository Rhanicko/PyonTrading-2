# Cleanup baseline - 2026-11-02

## Scope and evidence boundary

This baseline was captured from commit `c2683f49ebce7bf0ac54fd685261187186d1a7c7`
on branch `upgrade/advanced-analysis-foundation`. The worktree was clean before
the Phase 0 test-harness additions described below.

Runtime platform:

- Windows local development environment.
- Python 3.12.10, pytest 8.3.5 and Ruff 0.11.0.
- Node 24.19.0, npm 11.17.0, TypeScript 5.8.3, Vite 6.4.5, Vitest 5.0.5 and
  Playwright 1.52.x.
- Real MT5/provider integration was not exercised by these deterministic UI
  fixtures. Its current live availability remains **UNVERIFIED** here.

The app remains source-labelled and read-only. This audit did not send an MT5
order, change broker settings, write a migration, or create a live-trading
path.

## Inventory

| Area | Baseline inventory |
| --- | --- |
| Browser application | Vite/React entry: `frontend/src/main.tsx`; page orchestration: `frontend/src/App.tsx`; components: `ConnectionWizard`, `LiveResearchWatch`, `MarketReviewModal`, and `PriceChart`. |
| Client API surface | `frontend/src/services/api.ts` provides typed REST wrappers; quote updates use `/ws/live`. |
| REST API | 29 `/api` routes in `backend/app/api/routes.py`, including connection, symbols, quote, candles, analysis, source capabilities, research/pipeline/jobs/models/strategies/validation/operations, macro, Kronos status, research analysis, backtests, and local settings. |
| Broker/provider boundaries | `backend/app/adapters/mt5.py` is the MT5-only boundary. `calendar.py` reads the configured public calendar. `official_macro.py` reads BLS, BEA and Federal Reserve schedules. No provider call was made during this baseline. |
| Storage | SQLite/WAL initialization and additive migrations are in `backend/app/storage/database.py`; tables cover settings, journal/evidence, calendar cache, backtests, archived/quarantined candles, jobs/runs/labels, frozen decisions, paper labels, operations/audit, broker sessions, strategy journal, signal history, and strategy settings. |
| Background work | `backend/app/services/live.py` owns bounded quote polling; `backend/app/services/pipeline.py` owns completed-candle research work; `backend/app/services/research.py` assembles source-labelled research. |
| Local skill guides | 25 task-specific guides under `.agents/skills/`, including MT5 integrity, calendar watching, multi-timeframe research, risk governance, backtesting, training validation, order-flow provenance, and journaling. |

## Automated baseline

The following commands were run before a source repair:

| Command | Result |
| --- | --- |
| `backend/../.venv/Scripts/python.exe -m pytest -q` | **75 passed** in 20.00s. |
| `backend/../.venv/Scripts/python.exe -m ruff check app tests` | **All checks passed.** |
| `frontend/npm.cmd run typecheck` | Exit 0. |
| `frontend/npm.cmd run test` | **2 files / 4 tests passed** in 684ms. |
| `frontend/npm.cmd run build` | Exit 0; 43 modules transformed in 3.51s. |
| `frontend/npm.cmd run test:e2e` before Phase 0 viewport coverage | **6 passed** across Chromium and mobile Chromium in 14.4s. |

Phase 0 then added exact 1440px, 768px and 390px browser projects and a
desired-behaviour Validation assertion. That new E2E assertion failed in all
three projects: `Historical M5 research` resolved in the DOM but was hidden.
This is the intentional red regression test for Finding P0-01, not a claim that
the pre-repair UI passed.

## Before screenshots

Deterministic mocked-source screenshots were captured locally under the ignored
directory `output/playwright/phase0-baseline/` so they do not publish mock
market data in source control. Each of `chromium` (1440px), `tablet-chrome`
(768px), and `mobile-chrome` (390px) contains:

- `market-desk.png`
- `research-network.png`
- `validation.png`
- `history.png`
- `sources-rules.png`
- `market-review-modal.png`
- `disconnected-market-desk.png`

There are 21 baseline images. `validation.png` at every size shows that the
Backtesting Lab and Volume & Order Flow cards are absent while the Validation
view is active.

## Confirmed findings

| ID | Severity | Evidence | Regression risk and repair acceptance |
| --- | --- | --- | --- |
| P0-01 | High | `frontend/src/styles.css:28` uses `.lower-grid > article:nth-child(3), .lower-grid > article:nth-child(4) { display: none; }`. In browser, after selecting Validation, both target cards had `hidden=false` and computed `display=none`. The new E2E assertion failed at `frontend/tests/e2e/research-bots.spec.ts:323` in 1440px, 768px and 390px. | Replace positional hiding with the existing semantic `hidden={activeView !== "validation"}` state. Backtesting Lab and Volume & Order Flow must be visible, keyboard reachable, and tested in all three viewports. |
| P0-02 | Medium | `frontend/src/App.tsx:275-291` contains obsolete commented JSX for a legacy manual research summary. It does not render but obscures the current single-source `LiveResearchWatch` design. | Remove only the verified dead comment block; preserve the active watch, modal and no-order wording. |
| P0-03 | Medium | `frontend/src/App.tsx:267` always labels the chart `24H broker-candle view`, while `timeframe` is selectable and `chartWindowLimits` varies from M1 to D1 at line 11. | The label must state actual selected timeframe and loaded completed/forming-bar status without claiming a data span not present in the response. |
| P0-04 | Medium | `App.tsx:79` refreshes 12 independent API reads in one `Promise.all`. One rejected optional request prevents all snapshot state from being applied. | Split critical quote/connection/candle updates from optional research modules; retain last-good optional data with per-module status. Add fault-injection tests before changing behavior. |
| P0-05 | Medium | E2E fixtures contain one forming M5 bar in `research-bots.spec.ts`; the resulting baseline chart shows zero completed bars. The UI must make empty/forming-only data visibly distinct from loaded history. | Test loading, empty, stale and disconnected states separately; do not infer indicators or a 24-hour span from a forming-only response. |
| P0-06 | Review required | Current browser configuration originally covered only desktop and mobile. Phase 0 now adds exact desktop/tablet/mobile projects, but the current screen capture demonstrates dense research content on mobile. | Keep all three viewport projects. Validate no clipped navigation, controls or critical status values after every responsive change. |

## Phase 1 acceptance checklist

- [ ] Validation exposes Backtesting Lab, Volume & Order Flow, Strategy Journal,
  Paper Validation and Research Controls when active, with no positional CSS
  hiding.
- [ ] The obsolete App JSX comment is removed without altering runtime output.
- [ ] The chart context and forming-bar label are derived from selected
  timeframe and response evidence.
- [ ] Chart viewport compactness remains independent from historical warm-up
  data used by higher-timeframe calculations.
- [ ] Loading, unavailable, stale, empty and disconnected states are all
  visible and source-labelled.
- [ ] E2E assertions and screenshots cover 1440px, 768px and 390px, including
  modal and disconnected flows.
- [ ] No order path, fabricated market value, destructive migration, or source
  provenance regression is introduced.

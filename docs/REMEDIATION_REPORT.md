# Remediation report - 2026-11-03

This is a progress report, not a release or profitability claim. PyonTrading 2
remains a read-only research workstation. No MT5 order path, broker credential,
fabricated market value, synthetic fill, or destructive migration was added.

## Phase 0 - baseline proof

- Changed: added `docs/CLEANUP_BASELINE.md`, deterministic desktop/tablet/mobile
  browser coverage, and ignored before-screenshot capture support.
- Evidence: the baseline records the original commit, runtime versions, endpoint
  and storage inventory, 21 pre-change screenshots, and a computed-style probe.
- Checks: pre-change backend `75 passed`; frontend typecheck, Vitest, build, and
  browser checks are recorded in the baseline document.
- Remaining: real MT5 and external provider behavior are unverified because
  these checks use deterministic fixtures.

## Phase 1 - confirmed interface defects

- Changed: removed positional CSS rules that hid Validation cards and broadly
  hid research-panel children, removed obsolete commented JSX, and derived
  chart context/forming-bar labels from the actual selected timeframe and
  response candle counts.
- Evidence: `Historical M5 research` was intentionally red at 1440px, 768px,
  and 390px before the CSS change; it is now asserted in each browser project.
  Chart tests assert a forming-only response as `0 completed · 1 forming`.
- Checks: all three browser projects pass the live, disconnected, Validation,
  modal, history, and Sources & rules flows.
- Remaining: the legacy CSS file still needs incremental module extraction;
  selectors are not being removed based only on naming.

## Phase 2 - interface architecture evidence

- Changed: extracted shared visual tokens to `frontend/src/styles/tokens.css`,
  removed obsolete broad research-panel hiding selectors, and added
  `docs/CSS_ARCHITECTURE_AUDIT.md` with static and computed-style evidence.
- Evidence: at 1440 px the chart receives 1034 px while the sticky research
  panel receives 330 px; at 390 px the document has no horizontal overflow.
- Checks: the complete 15-case Playwright suite passes at desktop, tablet, and
  mobile dimensions.
- Remaining: feature-by-feature CSS extraction is deliberately staged because
  the legacy stylesheet still has repeated historical overrides.

## Phase 3 - calculation and viewport contract

- Changed: `fixtures/technical-golden.json` is a shared completed-candle OHLCV
  fixture. Frontend RSI/ATR now use the same Wilder initialization/smoothing as
  `backend/app/analysis/technical.py`; the forming candle is excluded. Chart
  viewport storage is now scoped by broker server, exact symbol, and timeframe,
  with a one-time compatible migration of the prior exact `XAUUSD` key.
- Evidence: `frontend/tests/chartIndicators.test.ts` and
  `backend/tests/test_technical_analysis.py` both assert the same RSI/ATR
  values from the shared fixture.
- Checks: frontend indicator tests and backend technical tests pass.
- Remaining: source precision is preserved by the existing typed broker API;
  a live terminal is still required to validate actual broker precision.

## Phase 4 - refresh and worker resilience

- Changed: snapshot refresh separates three critical market reads from optional
  modules, preserves last-good optional data, and reports the calendar failure
  without clearing a live quote/chart. Research refresh failures now appear in
  the watch card without overwriting the last verified state or clearing an
  unrelated broker-data error. The research pipeline now performs a cycle on
  one bounded worker, backs off after a failure/timeout, and records cycle,
  quote, M5 collection, event-loop-lag, failure, and pending-job metrics. MT5
  adapter lifecycle/read calls are serialized with an adapter-level lock.
- Evidence: the browser fault-injection test returns a calendar 503 while
  retaining the live quote and candle view. The pipeline test proves a blocking
  cycle does not stop an async heartbeat; the MT5 test proves concurrent
  initializations are serialized.
- Checks: backend suite passes `78`; Ruff passes. Frontend typecheck, Vitest
  (7 tests), and build pass. Playwright passes 15/15 across 1440px, 768px, and
  390px.
- Performance: the pipeline is intentionally capped at one background cycle;
  runtime metrics are exposed by the existing `/api/research/pipeline` status
  response. No live latency claim has been made.
- Remaining: provider-specific timeout behavior needs a connected terminal and
  provider fault environment to validate beyond deterministic doubles.

## Phase 6 - research semantics

- Changed: the M5-only pullback replay is now named `M5_TREND_PULLBACK` with an
  M5-specific version/source label. `net_points` remains API-compatible, but is
  explicitly documented and reason-coded as spread-adjusted rather than net
  P&L; commission, slippage, swap, and fill quality remain unavailable.
- Evidence: backtest tests require the corrected strategy ID, M5 label, and
  spread-only limitation.
- Checks: `backend/tests/test_backtesting.py` passes.
- Remaining: point-in-time H1/H4 historical alignment has not been added; the
  strategy is deliberately not described as higher-timeframe research.

## Current repair gates

| Area | State | Evidence / limitation |
| --- | --- | --- |
| UI defect repair | Passing deterministic checks | 15 Playwright cases across desktop, tablet, and mobile. |
| Frontend CSS architecture | In progress | Tokens and hiding-rule cleanup are complete; the 1,490-line legacy stylesheet still needs safe, selector-by-selector extraction. |
| Real MT5 integration | Unverified | No real terminal was opened or queried during this remediation. |
| Multi-pair scanner | Deferred | Requires broker-validated symbol registry and compatibility tests. |
| Training promotion | Deferred | Needs immutable datasets, chronological holdouts, source-backed costs, and manual approval. |

## Architecture snapshot

```text
MT5 terminal (read-only) -> MT5Adapter lock -> LiveService / ResearchPipeline worker
                                           -> source-labelled REST + WebSocket updates
Public calendar / official schedules -> ResearchCoordinator -> immutable research evidence
React workstation -> critical market refresh + optional module refresh -> source-labelled UI
```

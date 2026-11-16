# Live-update verification — 2026-11-16

Scope: keep the existing workstation live through WebSocket and AJAX updates,
with correctly scoped source data. No strategy thresholds, historical evidence,
model promotions, or broker-order capabilities were changed.

## Fixed paths

- MT5 symbol changes discard in-flight old-symbol quotes/candles and clear the
  cached quote. Observation writes retain the symbol that produced their data.
- Initial loads, periodic refreshes and WebSocket events share one in-flight
  research request. Optional modules no longer overwrite that research result.
- Broker/terminal/symbol/mode changes invalidate the previous live context.
  Research checks the connection before and after reading its windows. If an
  old-generation response is discarded, one immediate replacement is allowed;
  repeated changes fall back to the normal polling cycle rather than spinning.
- Foreign-symbol packets, late REST quotes, outdated chart responses and events
  from disposed sockets cannot replace the selected context.
- WebSocket closure immediately withdraws the last live quote. An open but
  silent socket also falls back to broker-backed AJAX quote/candle reads.
- GET requests time out after 15 seconds; scanner/chart requests are aborted
  when their source, timeframe or component is replaced.
- A slow chart request cannot swallow a newer timeframe selection. Regular live
  updates preserve the existing chart viewport and expanded confirmation panel.
- Research snapshots older than 15 seconds are not labelled current. The panel
  explicitly marks retained confirmation stages as the last review only.
- Calendar, completed-candle observations, strategy journal and operational
  gates now refresh in the background rather than remaining page-load snapshots.
  These optional reads are deduplicated separately from core research.

## Update timing

MT5 quote polling remains approximately two seconds. Research/supporting reads
run every five seconds and research also refreshes on completed M5 bar events.
The comparative H1 scanner refreshes every minute while its view is open and
remounts immediately when the connection identity changes. These are polling
cadences, not latency guarantees. Higher-timeframe conclusions still require
their own completed candles; a fresh quote cannot turn a rejected stage green.

## Verification

- Backend: `pytest -q` — 164 passed; one Starlette/AnyIO deprecation warning.
  Ruff passed. Three new service tests first reproduced the symbol-change races.
- Frontend: `npm.cmd test` — 20 passed; production build/typecheck passed.
- Browser: full 105-case suite passed after the initial fixes, followed by 27
  affected-case passes after chart/silent-stream fixes. Later supporting-data
  testing exposed a mobile connection-change retry gap; a deterministic test
  reproduced it before the final retry fix. The final 24 affected cases passed
  across desktop, tablet and mobile Chromium after that fix.
- Actual MT5/MetaQuotes-Demo XAUUSD browser observation at 08:57 PHT: one main
  document load, nine WebSocket quotes, four research snapshots, no overlapping
  research requests, 11 bots, six top-down stages, eight scanner rows, matching
  research/watch/confirmation timestamps, retained open panel and chart range.
  Desktop 1440px and mobile 390px had no horizontal document overflow. No browser
  errors or failed API responses; worker RUNNING, zero failures/pending jobs.
- A later actual-feed check at 09:03 PHT confirmed repeated calendar, observation,
  strategy-journal and operations AJAX requests without a document reload.

Raw evidence and screenshots are under `output/audit-2026-11-16/`:
`ajax-live-browser-verified.json`, `ajax-final-support.json`, and the
`ajax-live-verified-*.png` screenshots. The first live harness incorrectly counted
SPA navigation as a reload; its original artifact is retained separately. The
corrected harness counts actual main-document requests.

## Boundaries

Physical account switching was not performed; connection-switch failures were
exercised with controlled browser fixtures. The actual feed check covers the
currently connected MetaQuotes demo, not every broker/account combination.
Unconfigured cross-market sources and unavailable genuine order flow remain
explicitly unavailable. Rejected stages/withheld signals are not replaced with
invented agreement, confidence, or profitability. The system remains signal-only.

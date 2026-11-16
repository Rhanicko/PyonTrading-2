# Current state — 2026-11-16 PHT

Objective: apply the user's nine-phase testing/intelligence request to the existing signal-only workstation. No broker execution or model promotion is authorized here.

Latest follow-up: live WebSocket/AJAX source scoping, deduplication, stale-state
handling, chart request races and supporting-card refreshes. Current evidence and
remaining scope: `docs/LIVE_UPDATE_VERIFICATION_2026-11-16.md`. The earlier audit
and its figures below remain historical observations, not newly measured results.

Current dashboard follow-up: a viewport grid now reserves space for the USD
calendar and latest observation below the chart. The sidebar uses a compact,
content-sized surface rather than stretching its actions into empty space. Full
proof/top-down/bot details remain under `Review evidence`. A clock-derived,
DST-aware indicative session label appears beside PHT time and is independent
of broker availability and strategy-session windows. No signal gates, provider
connections, chart calculations or order boundaries changed.
Verified production build, 37 frontend unit tests and 30 final affected browser
cases across desktop/tablet/mobile. Live 1280x720 and 1920x1080 inspections showed
both support cards and sidebar controls inside the viewport, without page scroll.
Current evidence and test-run limits: `docs/DASHBOARD_SESSION_LAYOUT_2026-11-16.md`.
The earlier layout pass is retained in `docs/DASHBOARD_LAYOUT_VERIFICATION_2026-11-16.md`.

14:15 PHT follow-up: an active directional watch without displayable levels now
reads `SHORT/LONG SETUP PENDING`, names unconfirmed required stages, and explains
reported candle gaps instead of presenting a positive integrity assertion as the
failure reason. No entry/publication gates were loosened. Verified 20 frontend
unit tests, 21 affected desktop/tablet/mobile browser cases, six backend level
guard tests and production build. Live MT5 showed a pending short with close/risk
blockers; no overflow at 375/768/1024/1440px. Simulated confirmation showed the
existing indicative Entry/SL/TP1/TP2 automatically without a document reload.

## Verified starting state

MT5 MetaQuotes-Demo XAUUSD was LIVE around 07:27 PHT. Pipeline RUNNING, 339 completed jobs, zero current worker errors, 1,338 archived bars without decision evidence, 0 eligible proofs and automatic publications. Twenty-six continuity-checked paper labels; held-out directional result 1/6. Coverage gaps do not establish why the source was interrupted.

## Implemented changes

- Local-time session weekdays; linear MACD with identical EMA seeding/results. Same pinned 6,000-bar archive: 16.061 seconds before vs 10.335 seconds after; selected horizons and results identical before subsequent non-overlap policy change.
- Research rejects stale/future/duplicate timeframe windows. Prior-session context is explicitly labelled when the broker provides a current forming bar; timestamps remain unchanged.
- D1/H4, H1, M15, M5 and optional M1 top-down stages, timestamped setups/invalidation, additional publication gate; feature version v7. Indicative levels require confirmed top-down evidence.
- Comparative scanner of up to eight exact visible FX/metals aliases, relative currency movement and matched H1-return correlations. Context only; XAUUSD publication remains the validated product scope.
- Full news-risk window independent of display limit/order, and short post-event cooling windows.
- Async MT5 poller reads and actual broker completed-close payloads on WebSocket rollover.
- Risk gate rejects stale/negative tick age, crossed quotes and nonfinite contract values. Emergency stop and paused worker withhold automatic publication.
- Calibration excludes overlapping trials per strategy and reports spread-adjusted diagnostics plus three expanding folds before final hold-out. No promotion.
- Scanner, compact top-down panel, validation diagnostics UI added.
- Optional macro network fetching now runs separately and leaves cache snapshots responsive. Expired schedules are labelled delayed.
- Completed-bar events wake the existing research worker. Manual V5 review shares the automatic top-down snapshot.
- Live integration exposed a new walk-forward datetime serialization error; typed JSON persistence and next-cycle retry are fixed and regression-tested.

## Final verified checks

Backend: 161 passed, one dependency deprecation warning; Ruff and diff whitespace clean. Frontend: 18 unit tests and production build passed. Full Playwright suite: 90 passed, followed by 15 affected-case reruns after the final presentation edits. Real desktop/mobile browser navigation had no page/console/network errors or horizontal overflow.

Final artifact `output/audit-2026-11-16/live-final.json`: 26 read endpoints HTTP 200, seven timeframes with 300 valid/order-checked candles each, 12/12 concurrent health reads, protected routes 403, WebSocket quote/bar updates, 23 observations spanning more than 330 seconds, zero current worker failures. Two M5 reviews arrived 1.212 and 3.001 seconds after close. Last three comparable M1→M5 OHLC aggregations matched. SQLite integrity and foreign keys passed; six audit/archive tables retained every baseline row unchanged.

Full archive: 31,547 M5 bars. ICT reversal and M5 pullback were positive in validation and held-out spread-adjusted points, but costs are incomplete and no combined live-policy edge is established. There were 55 proof-checked runs and zero eligible/automatic published signals as of 08:20:49 PHT. Full findings and exact limitations: `docs/SYSTEM_AUDIT_2026-11-16.md`.

## Runtime and rollback

Server on 127.0.0.1:8765 serves the patched code and rebuilt frontend, connected to live MetaQuotes-Demo. Existing dirty worktree preserved. SQLite snapshot at `output/audit-2026-11-16/before.db` passed integrity check. Earlier failed/intermediate audit artifacts remain separately named. No commits, pushes, loosened publication gates or broker orders.

## Remaining independently actionable work

1. Verify broker-session schedules and distinguish expected closures from missing data; 1,338 historical decision gaps cannot be recreated with current inputs.
2. Add forward-only broker identity to legacy symbol-scoped runs before multi-broker comparisons.
3. Obtain complete costs and legitimate order-flow/context/official actual-release sources; validate structural scenarios without assuming fills.
4. Freeze a fresh independent forward/hold-out period and compare candidate strategies against the baseline before separate manual promotion.
5. Broader forex publication, full account/portfolio risk, external notifications and any optional ML model remain separate incomplete implementations. Current readiness is research, not validated paper profitability or demo/live execution.

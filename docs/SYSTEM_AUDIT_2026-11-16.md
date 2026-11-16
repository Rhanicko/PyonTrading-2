# PyonTrading 2 — Monday live audit and improvements

Date: 16 November 2026, Asia/Manila. The verified final observation finished at **08:20:49 PHT**. The application remains running locally on `127.0.0.1:8765`, connected to **MetaQuotes-Demo / XAUUSD**. This is a bounded engineering and research audit, not certification of profitability, continuous uptime, or demo/live execution readiness.

## Result

The current research flow operates on live broker data, processes completed candles, preserves evidence, and rejects incomplete setups. **Automatic publication remains zero**: there were 55 proof-checked historical research runs and no eligible proofs as of the final observation. The 26 continuity-checked legacy paper labels still have only 1 directional match in 6 held-out labels. Those labels measure direction at a fixed horizon, not TP/SL execution or net profit.

The requested nine phases are **partially implemented overall**. The repairs, top-down evidence, comparative scanner, training diagnostics, and bounded live checks below are implemented and verified. Cost-complete validation, a complete multi-market signal engine, licensed order flow, and account/portfolio execution controls remain incomplete. No model was promoted and no broker order was placed.

## Confirmed defects and changes

| Problem | Implemented behavior | Main source |
| --- | --- | --- |
| Sunday UTC was labelled weekend during Monday's Asian session | Session weekday checks use each market's local date; UTC fallback preserves date rollover | `backend/app/analysis/quality.py` |
| MACD repeatedly recomputed EMA prefixes | Linear recurrence with the same SMA seed and numeric results | `backend/app/analysis/technical.py` |
| Live quotes could accompany stale, future or duplicate research candles | Explicit timeframe timing failures; prior-session context keeps its original timestamp when a current broker forming bar exists | `backend/app/services/research.py` |
| No explicit D1/M1 confirmation path | D1/H4 bias, H1 direction, M15 setup, M5 trigger, optional M1 timing and risk stages | `backend/app/analysis/confluence.py` |
| A bearish structure event could qualify an otherwise bullish setup | Setup event direction must match the proposed context; pending setups remain pending | `backend/app/services/research.py` |
| Manual and automatic research could disagree about daily rejection | Manual V5 review derives from the shared snapshot and top-down gates; duplicated analysis branch removed | `backend/app/services/research.py` |
| A nearer low-impact release could hide a high-impact release | Risk selection examines the full risk window independently of the display limit, including post-release cooling windows | `backend/app/adapters/calendar.py`, `backend/app/services/research.py` |
| Terminal reads could block the async server | Quote/candle/database reads yield through the thread executor | `backend/app/services/live.py` |
| WebSocket close events used an earlier forming snapshot | Closed events now contain the broker's actual completed candle | `backend/app/services/live.py` |
| Research waited for a 30-second idle poll after a close | A completed M5 bar wakes the existing serialized worker immediately; idle polling remains a fallback | `backend/app/main.py`, `backend/app/services/pipeline.py` |
| Optional macro refreshes blocked snapshot reads and research | Separate bounded refresh worker, short cache lock, explicit expired-cache status and refresh errors | `backend/app/adapters/official_macro.py`, `backend/app/services/pipeline.py` |
| Weak risk checks accepted invalid contract/quote values | Reject stale/negative tick age, crossed quotes and nonfinite contract metadata | `backend/app/analysis/professional.py` |
| Emergency stop did not gate qualified alerts | Stop/paused state withholds publication and levels; persistence rechecks current controls | `backend/app/services/research.py`, `backend/app/services/pipeline.py` |
| Longer calibration horizons reused overlapping trials | One non-overlapping trial per strategy at a time; zero training score is no longer ranked below negative scores | `backend/app/analysis/training.py` |
| New walk-forward timestamps failed registry JSON persistence | Typed JSON serialization preserves timestamp strings; a failed save does not postpone retry for six hours | `backend/app/services/pipeline.py` |

The registry serialization bug was introduced during this enhancement and discovered by the real-data run. Its reproduction and retry regression tests now pass. Intermediate audit files are retained as evidence; they are not presented as final clean runs.

## Phase-by-phase status

| Requested phase | Verified delivery | Remaining scope |
| --- | --- | --- |
| 1. Real-time testing | Live connection, quotes/specifications, 26 read endpoints, seven chart timeframes, WebSocket, concurrent reads, protected routes, tests and source failures | No independent second-feed price certification, long-duration soak or exhaustive dead-code proof |
| 2. Top-down validation | Six timeframe observations, separate stages, source timestamps, known-at setups, invalidation reference, M1 optional, new publication gate | The rule set is unvalidated for profitability; not every proposed ICT pattern has an independent validated detector |
| 3. Broader intelligence | Up to eight exact visible FX/metals symbols, descriptive ranking, relative signed currency returns, matched-H1-return correlations/exposure flags, current session/regime and calendar sources | Scanner is comparative context; automatic forex signals and a portfolio engine are not implemented. DXY/yield/oil/volatility symbols remain unconfigured |
| 4. Signal quality | Eleven publication checks, daily-bias veto, separate pending/rejected stages, source/risk checks, indicative levels withheld on top-down rejection | Existing ATR 1R/2R levels are unvalidated references. Structural trade stops, calibrated probabilities and complete execution-cost approval are not established |
| 5. Training/validation | 60/20/20 split, three expanding validation folds before the final 20%, horizon selection on training only, non-overlap, versioned registry, spread-adjusted diagnostics | No strategy has been promoted. No proven net edge, account-return Sharpe ratio, or full live-pipeline historical replay |
| 6. Risk management | Source/contract/spread/event vetoes, emergency stop, pause controller, duplicate publication prevention | Position sizing, margin checks, portfolio daily loss/drawdown limits and correlated-position enforcement are not implemented as an execution system |
| 7. Reliability/UI | Shared manual/automatic calculation, async source reads, optional-provider isolation, compact confirmation panel, scanner and diagnostic drawers, reduced default proof detail | No broad redesign or speculative removal of supposedly unused code. The unavailable graph index limited exhaustive dependency/dead-code analysis |
| 8. Live validation | Twenty-three snapshots over more than 330 seconds after API/archive checks, two new M5 research decisions, frozen evidence and honest abstention | No automatic directional signal was observed. No TP/SL outcomes or broker fills can be validated from that absence |
| 9. Final verification | Tests/build, live browser flows, data integrity, unchanged historical audit rows, raw artifacts and this report | Readiness is research only; not validated demo or real-money execution |

## Broker-data and browser evidence

Final raw report: `output/audit-2026-11-16/live-final.json`.

- All 26 audited read endpoints returned HTTP 200. Individual payload statuses still distinguish live, delayed, not configured and unavailable features.
- M1, M5, M15, M30, H1, H4 and D1 each returned 300 candles: 299 completed and one forming. Ordering, OHLC bounds and no-future-completed-bar checks passed for all seven samples.
- The last three comparable completed M5 candles matched aggregation of their five completed M1 candles exactly for OHLC. This verifies synchronization within this broker sample, not agreement with a separate provider.
- Observed contract values were positive and bid/ask spread matched the reported point calculation.
- WebSocket delivered `heartbeat`, `quote` and `bar_update`. Completed-close payload correctness and wake-up behavior also have regression tests.
- Twelve concurrent health reads succeeded. Unauthenticated pipeline mutation and account-financial reads returned 403; the worker stayed enabled.
- A real manual review returned HTTP 200 with `RESEARCH_SCREEN_V5_SHARED_TOP_DOWN` and preserved its rejection evidence.
- Actual browser navigation covered Market desk → Research network → Validation → History and responsive Research network. Eight scanner rows and six confirmation stages rendered. No page errors, console errors, failed requests or HTTP API errors occurred in that check. Document widths matched 1440px and 390px viewports without horizontal page overflow.
- BLS, BEA and Federal Reserve schedule endpoints were available at final inspection. These adapters do not provide independently verified actual/forecast release values; BEA/Fed next-release times are not machine-verified.
- Cross-market exact symbols, licensed futures order flow, and Kronos remain explicitly unconfigured. The connected broker is not HFM.

Screenshots: `verified-desk-desktop.png` and `verified-research-mobile.png` in the same output directory. Earlier screenshots and audit runs remain there with their original filenames.

## Performance measurements

On the same saved 6,000 completed bars, calibration took **16.061 seconds before** the MACD change and **10.335 seconds after**: about **35.7% less elapsed time**. All nine selected horizons and result totals were identical at that stage. This was a local measurement, not a controlled hardware benchmark. The later non-overlap policy intentionally changes trial counts/results.

Before event-driven wake-up, one observed review completed 26.766 seconds after the M5 close. Final observed reviews completed at:

- 08:15:01.211923 PHT for the 08:15 close: **1.212 seconds**.
- 08:20:03.000601 PHT for the 08:20 close: **3.001 seconds**.

These two observations do not establish a guaranteed latency bound. The final worker had zero failures and no current error during the final audit. Initial calibration/backfill still took about 17.4 seconds while the HTTP service was available. The intermediate run recorded a registry TypeError, which prompted the serialization/retry fix. Optional-provider isolation addressed a separately reproduced blocking condition; its relationship to earlier startup delays is not established. Retain longer restart/load testing as an operational priority.

## Historical findings

The final full-archive calculation used **31,547 completed MetaQuotes-Demo M5 bars**, from 2026-05-17 23:35 UTC through the 2026-11-16 00:10 UTC close. Values below are **recorded-spread-adjusted points**, not dollars, fills, or complete net profit.

| Standalone strategy | Validation points | Held-out points | Positive expanding folds |
| --- | ---: | ---: | ---: |
| Price structure baseline | +6,864 | −13,478 | 3/3 |
| ICT liquidity reversal | +2,113 | +5,401 | 3/3 |
| Momentum continuation | +18,322 | −12,397 | 3/3 |
| M5 trend pullback | +23 | +9,285 | 2/3 |
| Liquidity sweep proxy | −9,527 | +2,022 | 0/3 |
| Opening-range breakout | −18,457 | −9,846 | 2/3 |

VWAP tick-proxy momentum, volume-profile auction and futures-flow confirmation had insufficient comparable source/trial evidence; their results are unavailable, not zero returns.

ICT reversal and trend pullback deserve further research, but these are standalone candle strategies, not a replay of the current live ensemble. The pullback's validation margin is particularly thin. Commission, slippage, swap, intrabar path and actual fill quality remain missing. The final 20% is excluded from automated selection, but repeated human audits have already inspected this period; a new future or genuinely unseen period is required for a fresh independent test. These results cannot justify a win probability or model promotion.

## Verification commands and preservation

- Backend: `python -m pytest -q` — **161 passed**, one Starlette/AnyIO deprecation warning.
- Ruff and Git whitespace checks — passed.
- Frontend: `npm.cmd run test` — **18 passed**; `npm.cmd run build` — passed.
- Browser suite: **90 passed** across Chromium desktop, tablet and mobile. After the final modal/proof presentation edits, **15 affected cases** passed again across those projects. These tests use controlled fixtures; the real browser check above used the running broker-connected backend.
- `scripts/audit-realtime.py` performed the real HTTP/WebSocket/archive/observation run. To repeat: `.\.venv\Scripts\python.exe scripts/audit-realtime.py --output output/audit-repeat.json --seconds 330 --validate-archive`.
- SQLite integrity check: `ok`; foreign-key violations: zero. Comparing the saved baseline against current rows in `signal_history`, `frozen_research_decisions`, `research_runs`, both label tables and `market_candles` found **zero changed or missing baseline rows**.
- Database backup: `output/audit-2026-11-16/before.db`. Earlier decisions/labels stay in the audit trail. Existing unrelated worktree edits were preserved. No commit, push, deployment or destructive cleanup was performed.

## Remaining priorities

1. Obtain verified broker-session schedules so expected closures can be distinguished from missing data. The historical coverage gap remains 1,338 archived bars without original decision-time evidence; those decisions cannot honestly be recreated with today's quote/calendar.
2. Add forward-only broker identity to legacy symbol-scoped research records before multi-broker performance comparisons. Current validation explicitly labels that limitation.
3. Obtain real commission/slippage/swap and bid/ask history, then validate proposed stops/targets without assuming OHLC touches were fills.
4. Use a fresh, frozen forward period and new hold-out for the promising standalone candidates and the combined top-down policy. Add regime comparisons and a separate manual champion/challenger decision.
5. Configure legitimate cross-market sources and official actual-release data. Licensed executed order flow must remain unavailable until an appropriate provider is connected.
6. Implement and independently validate any additional forex strategy, account/portfolio risk model, notification service or optional model as a separate research feature. Current desktop alerts depend on the page staying open and permission being granted; the Python worker runs independently of the page while the app process remains running.

Readiness: usable for source-labelled research and further forward validation. Profitable signal provision, complete paper performance, demo execution and real-money trading are **not validated**.

Primary implementation references: [MT5 bar numbering and forming bar](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py), [MT5 symbol specifications](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py), [MT5 candle time/range semantics](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py). Operational values in this report come from the local artifacts, not those documentation pages.

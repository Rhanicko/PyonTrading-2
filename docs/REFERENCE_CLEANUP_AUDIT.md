# Runtime Reference Cleanup Audit

Date: 2026-11-03

## Purpose

Before deleting or merging apparently overlapping PyonTrading code, this audit
checks runtime construction, routes, imports, storage references, and tests.
It is intentionally conservative: no production code was removed based only on
a filename or a similar name.

## Confirmed runtime roots

| Area | Runtime evidence | Test evidence | Cleanup decision |
| --- | --- | --- | --- |
| Live provider lifecycle | `app.main` constructs `LiveService`; it starts before the research pipeline and stops it during shutdown. | `tests/test_live_service.py` | Keep. |
| Research snapshot logic | `app.main` constructs `ResearchCoordinator`; `/api/research`, `/api/analysis`, and the worker call it. | `tests/test_research_service.py` | Keep. |
| Background research | `app.main` constructs and starts `ResearchPipeline`; `/api/research/pipeline` and `/api/research/jobs` expose its status. | `tests/test_research_pipeline.py` | Keep. |
| Backtesting | `/api/backtests/run` uses `BacktestCoordinator`, which uses `analysis.backtesting` and stores immutable run summaries. | `tests/test_backtest_service.py`, `tests/test_backtesting.py` | Keep. |
| Source setup | `SourceSetupService` is imported by routes and calls `CrossMarketContextService`. | `tests/test_source_setup.py`, `tests/test_cross_market.py` | Keep. |
| Durable research storage | `research_jobs`, `research_runs`, labels, frozen decisions, signal history, and backtests are referenced by routes and pipeline methods. | pipeline, research, backtest, and storage tests | Keep; do not drop tables or migrations. |

## Route inventory

`backend/app/api/routes.py` is the sole `APIRouter` mounted by `app.main`.
It serves 29 REST endpoints under `/api`, including live data, research,
pipeline/jobs, validation, operations, source capability, and backtest paths.
There is no duplicate route module to remove.

## Findings

- `analysis/backtesting.py` and `analysis/training.py` share the historical
  signal model deliberately: training imports the catalog and evaluator rather
  than reimplementing them.
- `services/research.py` and `services/pipeline.py` have different ownership:
  the former evaluates a snapshot; the latter schedules, persists, labels, and
  exposes worker health. They must not be merged or deleted as duplicates.
- `storage/database.py` is a large shared persistence boundary with additive
  migrations. Splitting it requires a separate import, route, and migration
  plan; direct deletion would risk breaking durable evidence and signal history.

## Deferred cleanup

The primary remaining code-quality target is a staged split of
`storage/database.py` by ownership (signal history, pipeline runs, operations,
and backtests) with compatibility imports and migration tests. It was not
performed in this remediation pass because it is a structural change, not a
safe duplicate removal.

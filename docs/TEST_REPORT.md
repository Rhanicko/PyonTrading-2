# Test report

## 2026-10-23 local implementation verification

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `backend/..\\.venv\\Scripts\\python.exe -m pytest` | 64 passed |
| Backend style | `backend/..\\.venv\\Scripts\\python.exe -m ruff check app tests` | All checks passed |
| Frontend typecheck | `frontend/npm.cmd run typecheck` | Passed |
| Frontend unit tests | `frontend/npm.cmd test` | 2 files, 3 tests passed |
| Frontend production build | `frontend/npm.cmd run build` | Passed |
| Browser E2E | `frontend/npm.cmd run test:e2e` with temporary Vite server | 4 passed: Chromium and Pixel 5, disconnected and live-fixture flows |
| Local API smoke | `GET /api/health`, `/api/symbols`, `/api/research/strategies`, `/api/research/models`, `/api/research/jobs`, `/api/kronos/status` | Verified locally against the running local server |

## Local API smoke evidence

- `/api/health` returned `ready: true` and `LIVE` for the connected local MT5
  terminal at the time of the check.
- `/api/symbols` returned two exact broker-discovered gold symbols; no alias was
  guessed.
- `/api/research/strategies` returned three enabled-by-default local research
  votes. The mutation path is covered by the SQLite and operator-token tests.
- `/api/research/jobs` reported the background worker as `RUNNING` with seven
  named workers.
- `/api/kronos/status` returned `NOT_AVAILABLE` / `NOT_CONFIGURED` with
  `NO_SIGNAL_AUTHORITY`; no model, weights or forecast path was invented.

## Limits of this verification

The browser E2E suite uses typed local fixtures; it does not prove a particular
broker continues to deliver live data. The source smoke test is point-in-time,
and no licensed futures-flow provider, commission/slippage source, Kronos
weight, multi-pair source or external model was installed or tested.

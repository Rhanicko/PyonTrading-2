# Tooling

| Tool | Purpose | Current use | Install/remove notes |
| --- | --- | --- | --- |
| Python 3.11/3.12 x64 | Local backend runtime | Required | Installed outside the repository. |
| MetaTrader5 Python wheel | Read-only local terminal adapter | Required for live MT5 | Pinned in `backend/requirements.txt`; no credentials are stored. |
| FastAPI/Uvicorn | Local API and compiled frontend host | Required | Pinned in `backend/requirements.txt`. |
| SQLite (stdlib) | Local WAL settings, archive and journals | Required | No server or secret required. |
| React/Vite/TypeScript | Local dashboard build | Required | Locked by `frontend/package-lock.json`. |
| Lightweight Charts | Chart rendering | Required | Retain vendor attribution in the UI. |
| pytest/Ruff/Vitest/Playwright | Test and static-check tooling | Required for verification | Run through the documented local scripts. |
| Kronos | Optional forecasting research | Not installed | Review the upstream license, dependencies, model weights, source hash, CPU budget and offline baseline plan before enabling. |
| Licensed futures-flow provider | Genuine executed flow/depth | Not configured | Never substitute retail MT5 tick volume for this source. |

No third-party agent skill, model weight, hosted service, provider credential, or
global Codex setting is installed by default.

# Troubleshooting

## `PythonUsable: False`

Install Python 3.11 or 3.12 x64 from python.org, choose the installer option to add Python to PATH, reopen PowerShell, run `python --version`, then rerun `./setup.ps1`.

## MT5 reports disconnected

PyonTrading starts a configured or conventional MetaTrader 5 installation once at application startup. Sign into the intended broker account in MT5 itself. If your terminal is installed somewhere non-standard, set `PYON_MT5_TERMINAL_PATH` in a local `.env`-loading environment. The application does not request a broker password and does not relaunch MT5 after you close it.

## No gold symbol is selectable

In MT5 Market Watch, search and add the exact broker symbol. Then choose it from PyonTrading 2's discovered list. Do not enter a guessed alias.

## Port 8765 is in use

Close the other local process using the port, or set `PYON_PORT` before starting. The standard launcher intentionally stops rather than binding to an unexpected interface/port.

## Cross-market context is `NOT CONFIGURED`

This is expected until you set an exact symbol supplied by your connected broker for the relevant feature (`PYON_DXY_SYMBOL`, `PYON_US10Y_SYMBOL`, `PYON_WTI_SYMBOL`, or `PYON_VOLATILITY_SYMBOL`) and add it to MT5 Market Watch. PyonTrading 2 will not guess aliases or replace a missing broker context source with an internet price.

## Official macro schedule is unavailable

The official BLS, BEA and Federal Reserve readers use public schedule pages with bounded network calls. A source error means schedule provenance is unavailable at that moment; it does not mean there is no news risk. The public weekly calendar is separately labelled and remains informational.

## Paper kill switch endpoint returns `403`

Set a strong `PYON_OPERATOR_TOKEN` in the local server environment, restart PyonTrading 2, and send it only as `X-Pyon-Operator-Token` to the local control endpoint. The browser does not store that secret. The kill switch only blocks new paper-candidate records; it cannot place or affect a broker order.


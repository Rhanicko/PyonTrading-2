@echo off
setlocal
cd /d "%~dp0"
set "PYON_NO_BROWSER="
if /I "%~1"=="--no-browser" set "PYON_NO_BROWSER=1"
if not exist ".venv\Scripts\python.exe" (echo Setup has not completed. Run setup.bat first. & exit /b 1)
if not exist "frontend\dist\index.html" (echo Frontend assets are missing. Run setup.bat first. & exit /b 1)
if not defined PYON_NO_BROWSER start "PyonTrading 2" http://127.0.0.1:8765
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765


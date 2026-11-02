@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11 or 3.12 x64 is required. Install it from python.org, reopen Command Prompt, then run this file again. & exit /b 1)
python -c "import sys; assert (3,11) <= sys.version_info < (3,13), 'Use Python 3.11 or 3.12.'" || exit /b 1
if not exist ".venv\Scripts\python.exe" python -m venv .venv || exit /b 1
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt || exit /b 1
where npm.cmd >nul 2>nul || (echo Node.js and npm are required to build the dashboard. & exit /b 1)
pushd frontend
call npm.cmd install || (popd & exit /b 1)
call npm.cmd run build || (popd & exit /b 1)
popd
pushd backend
..\.venv\Scripts\python.exe -c "from app.storage.database import initialize_database; from app.config import settings; initialize_database(settings.database_path)" || (popd & exit /b 1)
popd
echo Setup complete. Run Start-PyonTrading2.bat


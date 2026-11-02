$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

& "$PSScriptRoot\environment-report.ps1"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python 3.11 or 3.12 x64 is required. Install it from python.org, ensure it is on PATH, and run this command again.' }
& $python.Source -c "import sys; assert (3,11) <= sys.version_info < (3,13), 'Use Python 3.11 or 3.12 for this pinned setup.'"
if ($LASTEXITCODE -ne 0) { throw 'A usable Python 3.11 or 3.12 interpreter was not found.' }

if (-not (Test-Path '.venv\Scripts\python.exe')) { & $python.Source -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Node.js LTS with npm is required to build the local dashboard.' }
Push-Location frontend
& npm.cmd install
& npm.cmd run build
Pop-Location

Push-Location backend
& ..\.venv\Scripts\python.exe -c "from app.storage.database import initialize_database; from app.config import settings; initialize_database(settings.database_path)"
Pop-Location
Write-Host 'Setup complete. Start with .\Start-PyonTrading2.ps1' -ForegroundColor Green


$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$port = if ($env:PYON_PORT) { [int]$env:PYON_PORT } else { 8765 }
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Setup has not completed. Run .\setup.ps1 first.' }
if (-not (Test-Path 'frontend\dist\index.html')) { throw 'Frontend assets are missing. Run .\setup.ps1 first.' }
if (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is already in use. Stop the other local process or change PYON_PORT before starting." }
Start-Process "http://127.0.0.1:$port"
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $port


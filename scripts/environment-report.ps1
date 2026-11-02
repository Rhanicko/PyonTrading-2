$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

function Test-RealPython {
  $candidate = Get-Command python -ErrorAction SilentlyContinue
  if (-not $candidate) { return $false }
  $null = & $candidate.Source -c "import sys" 2>$null
  return $LASTEXITCODE -eq 0
}

$mt5Paths = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA, $env:APPDATA) |
  Where-Object { $_ } |
  ForEach-Object { Get-ChildItem -LiteralPath $_ -Filter terminal64.exe -Recurse -ErrorAction SilentlyContinue } |
  Select-Object -ExpandProperty FullName -First 8
$portInUse = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue

[pscustomobject]@{
  Windows = (Get-CimInstance Win32_OperatingSystem).Caption
  Architecture = (Get-CimInstance Win32_OperatingSystem).OSArchitecture
  PythonUsable = (Test-RealPython)
  Node = if (Get-Command node -ErrorAction SilentlyContinue) { (node --version) } else { 'NOT FOUND' }
  MT5Terminal = if ($mt5Paths) { $mt5Paths -join '; ' } else { 'NOT DETECTED' }
  Port8765 = if ($portInUse) { 'IN USE' } else { 'AVAILABLE' }
  Project = $projectRoot
} | Format-List

if (-not (Test-RealPython)) { Write-Host 'BLOCKER: Install Python 3.12 x64 from python.org and enable its PATH option, then rerun .\setup.ps1.' -ForegroundColor Yellow }
if (-not $mt5Paths) { Write-Host 'BLOCKER: Install MT5, open it, and log into your broker before launching PyonTrading 2.' -ForegroundColor Yellow }


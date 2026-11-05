<#
  Einmalige Einrichtung: Python-venv, Backend-Abhängigkeiten, Frontend-Build.
  Aufruf im Projektverzeichnis:
    powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Bevorzugt den offiziellen Python-Launcher (python.org). MSYS2/Cygwin-Python
# kann die benötigten Binärpakete (pydantic-core, argon2-cffi, lxml) nicht installieren.
$pyExe = $null
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in "3.13", "3.12", "3.11") {
        & py "-$v" -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $pyExe = "py"; $pyArgs = @("-$v"); break }
    }
}
if (-not $pyExe) {
    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe")) {
        if (Test-Path $candidate) { $pyExe = $candidate; break }
    }
}
if (-not $pyExe) {
    throw "Kein offizielles Python 3.11+ gefunden. Installation: winget install Python.Python.3.12 --scope user"
}
Write-Host "==> Python: $pyExe $pyArgs" -ForegroundColor Cyan

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
    Write-Host "==> Erzeuge virtuelle Umgebung .venv" -ForegroundColor Cyan
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "venv konnte nicht erstellt werden" }
}

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip --quiet
Write-Host "==> Installiere Backend-Abhängigkeiten" -ForegroundColor Cyan
& $venvPy -m pip install -r backend\requirements-dev.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "pip install fehlgeschlagen" }

Write-Host "==> Installiere Frontend-Abhängigkeiten und baue Frontend" -ForegroundColor Cyan
Push-Location frontend
npm install --no-fund --no-audit
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install fehlgeschlagen" }
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Frontend-Build fehlgeschlagen" }
Pop-Location

Write-Host ""
Write-Host "Fertig. Nächste Schritte:" -ForegroundColor Green
Write-Host "  1) Administrator anlegen:  .\.venv\Scripts\python.exe -m backend.cli create-admin --username admin"
Write-Host "  2) Server starten:         powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1"
Write-Host "  3) Browser:                http://127.0.0.1:8000"

<#
  Startet den ADS-TEC Security Manager mit einem Befehl:
    - richtet beim ersten Mal alles ein (venv, Pakete, Frontend-Build)
    - fragt beim ersten Mal nach einem Administrator-Konto
    - startet den Server und öffnet den Browser
  Aufruf: Doppelklick auf start.cmd  oder  .\start.cmd
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$Host.UI.RawUI.WindowTitle = "ADS-TEC Security Manager"

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy) -or -not (Test-Path "frontend\dist\index.html")) {
    Write-Host "==> Ersteinrichtung ..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "setup.ps1")
}

$port = if ($env:ASM_PORT) { $env:ASM_PORT } else { "8000" }
$url = "http://127.0.0.1:$port"

# Einmal-Schlüssel für die Ersteinrichtung im Browser. Wird nur genutzt, solange noch
# kein Benutzer existiert, und steht im URL-Fragment (wird nie an den Server gesendet).
$bytes = New-Object byte[] 24
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$env:ASM_SETUP_TOKEN = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
$browserUrl = "$url/#setup=$($env:ASM_SETUP_TOKEN)"

# Browser öffnen, sobald der Server antwortet
Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    "-NoProfile", "-Command",
    "for (`$i = 0; `$i -lt 120; `$i++) { try { Invoke-WebRequest -UseBasicParsing '$url/api/health' | Out-Null; Start-Process '$browserUrl'; break } catch { Start-Sleep -Milliseconds 500 } }"
)

Write-Host ""
Write-Host "ADS-TEC Security Manager: $url" -ForegroundColor Green
Write-Host "Zum Beenden dieses Fenster schließen oder Strg+C drücken." -ForegroundColor DarkGray
Write-Host ""
& $venvPy -m backend

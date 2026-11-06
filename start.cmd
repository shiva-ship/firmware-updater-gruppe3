@echo off
rem ADS-TEC Security Manager starten – LIVE-Modus (echte Geräte). DEMO: start-demo.cmd
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 pause

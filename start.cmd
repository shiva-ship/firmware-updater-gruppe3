@echo off
rem ADS-TEC Security Manager starten (Doppelklick oder: .\start.cmd)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
if errorlevel 1 pause

@echo off
rem ADS-TEC Security Manager im DEMO-Modus starten (simulierte Geräte, keine Geräteänderungen)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -Mode demo
if errorlevel 1 pause

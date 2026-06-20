@echo off
setlocal

cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\start_green_direct_app.ps1" -Port 8503 %*
exit /b %ERRORLEVEL%

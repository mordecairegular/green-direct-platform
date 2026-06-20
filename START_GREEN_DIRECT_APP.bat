@echo off
setlocal

cd /d "%~dp0"
echo ==========================================
echo Green Direct Planning Platform
echo ==========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_green_direct_app.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo Launcher exited with code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%

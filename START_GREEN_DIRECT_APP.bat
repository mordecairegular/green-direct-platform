@echo off
setlocal

cd /d "%~dp0"
set "PORT=8501"
set "APP_URL=http://localhost:%PORT%"
set "PYTHONPATH=%CD%\src"

echo ==========================================
echo Green Direct Power Simulation Tool
echo ==========================================
echo.
echo Project: %CD%
echo URL:     %APP_URL%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$open = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if ($open) { Start-Process '%APP_URL%'; exit 0 } else { exit 1 }"

if "%ERRORLEVEL%"=="0" (
  echo The app is already running. Browser opened.
  echo You can close this window.
  pause
  exit /b 0
)

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

echo Starting Streamlit...
echo Keep this window open while using the app.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Sleep -Seconds 5; Start-Process '%APP_URL%'"
"%PYTHON_EXE%" -m streamlit run "src\green_direct\ui\app.py" --server.port %PORT%

echo.
echo Streamlit has stopped.
pause

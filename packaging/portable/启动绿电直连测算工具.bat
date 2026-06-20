@echo off
setlocal

cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set "RUNTIME_TEMP=%CD%\.runtime\tmp"
if not exist "%RUNTIME_TEMP%" mkdir "%RUNTIME_TEMP%"
set "TEMP=%RUNTIME_TEMP%"
set "TMP=%RUNTIME_TEMP%"
set "TMPDIR=%RUNTIME_TEMP%"
if not defined GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT set "GREEN_DIRECT_ENABLE_RUNTIME_SNAPSHOT=1"
if not defined BROWSER_PATH if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER_PATH if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_PATH=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER_PATH if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER_PATH if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_PATH=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER_PATH if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "BROWSER_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"

echo ==========================================
echo Green Direct Planning Platform
echo ==========================================
echo.
echo App folder: %CD%
echo Temp folder: %RUNTIME_TEMP%
if defined BROWSER_PATH echo Browser:    %BROWSER_PATH%
echo.

if exist ".python\python.exe" (
  set "PYTHON_EXE=.python\python.exe"
) else if exist ".runtime\Scripts\python.exe" (
  set "PYTHON_EXE=.runtime\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

for /f "usebackq tokens=*" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "for ($p = 8503; $p -le 8515; $p++) { if (-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)) { Write-Output $p; exit 0 } }; exit 1"`) do set "PORT=%%P"

if not defined PORT (
  echo No available localhost port found in 8503-8515.
  pause
  exit /b 1
)

set "APP_URL=http://localhost:%PORT%"
echo URL:        %APP_URL%
echo Python:     %PYTHON_EXE%
echo.

echo Starting app. Please wait...
echo Keep this window open while using the app.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "Start-Sleep -Seconds 6; Start-Process '%APP_URL%'"
"%PYTHON_EXE%" -m streamlit run "src\green_direct\ui\app.py" --server.address localhost --server.port %PORT% --server.headless true --browser.gatherUsageStats false

echo.
echo App service has stopped.
pause

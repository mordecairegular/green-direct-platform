@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

echo ==========================================
echo Green Direct Local Trial
echo ==========================================
echo.
echo This launcher keeps the Streamlit web workflow.
echo It creates .venv and installs dependencies on first run.
echo.

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "BOOTSTRAP_PY="
  where python >nul 2>nul
  if not errorlevel 1 set "BOOTSTRAP_PY=python"
  if not defined BOOTSTRAP_PY (
    where py >nul 2>nul
    if not errorlevel 1 set "BOOTSTRAP_PY=py -3"
  )
  if not defined BOOTSTRAP_PY (
    echo Python was not found.
    echo Please install Python 3.10 or newer, then run this file again.
    pause
    exit /b 1
  )
  echo Creating local Python environment...
  !BOOTSTRAP_PY! -m venv .venv
  if errorlevel 1 (
    echo Failed to create .venv.
    pause
    exit /b 1
  )
  set "PYTHON_EXE=.venv\Scripts\python.exe"
)

set "REQ_FILE=requirements-runtime.txt"
if not exist "%REQ_FILE%" set "REQ_FILE=requirements.txt"

"%PYTHON_EXE%" -c "import streamlit, pandas, numpy, plotly, kaleido, chardet, openpyxl, xlsxwriter, yaml, pydantic" >nul 2>nul
if errorlevel 1 (
  echo Installing required Python packages...
  "%PYTHON_EXE%" -m pip install --upgrade pip
  if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
  )
  "%PYTHON_EXE%" -m pip install -r "%REQ_FILE%"
  if errorlevel 1 (
    echo Failed to install dependencies.
    echo If your network blocks pip, try a company network or ask for an offline package.
    pause
    exit /b 1
  )
) else (
  echo Dependencies look ready.
)

echo.
call "%~dp0START_GREEN_DIRECT_APP.bat" %*

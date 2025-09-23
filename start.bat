@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Change to the directory of this script
pushd "%~dp0"

REM Default port
set PORT=8011

REM Read port from settings.txt if present (expects a line starting with: port=NNNN)
if exist settings.txt (
  for /f "tokens=1,2 delims==" %%A in ('findstr /b /i "port=" settings.txt') do (
    if /i "%%A"=="port" set PORT=%%B
  )
)

REM Ensure venv exists
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment. Ensure Python is installed and on PATH.
    goto :end
  )
)

REM Upgrade pip and install dependencies
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
if exist requirements.txt (
  echo Installing dependencies - this may take a minute...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Failed to install dependencies. Please check your internet connection.
    goto :end
  )
)

REM Open the dashboard in the default browser after a short delay
start "" powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:%PORT%/'"

REM Start the FastAPI server using the venv's Python
echo Starting server on http://127.0.0.1:%PORT%/
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port %PORT%

:end
popd
endlocal

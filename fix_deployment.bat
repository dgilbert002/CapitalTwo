@echo off
echo.
echo ==========================================
echo CAPITAL TWO DEPLOYMENT FIX
echo ==========================================
echo.

echo Step 1: Creating/activating virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo Created new virtual environment
)
.venv\Scripts\activate

echo.
echo Step 2: Uninstalling any existing capitalcom packages...
.venv\Scripts\pip uninstall -y capitalcom capitalcom-python 2>nul

echo.
echo Step 3: Installing EXACT package versions from working server...
echo Installing capitalcom==1.0.4 (the version from working laptop)
.venv\Scripts\pip install --force-reinstall capitalcom==1.0.4

echo.
echo Step 4: Installing other requirements from exact versions file...
if exist requirements_exact.txt (
    echo Using requirements_exact.txt with exact versions from working system
    .venv\Scripts\pip install -r requirements_exact.txt
) else (
    echo requirements_exact.txt not found, using requirements.txt
    .venv\Scripts\pip install -r requirements.txt
)

echo.
echo Step 5: Running diagnostic test...
.venv\Scripts\python test_api_diagnostic.py

echo.
echo ==========================================
echo DEPLOYMENT FIX COMPLETE
echo ==========================================
echo.
echo If authentication still fails, check:
echo 1. System time is synchronized (run: w32tm /resync)
echo 2. No corporate proxy/firewall blocking Capital.com
echo 3. API key hasn't been regenerated/changed
echo.
pause

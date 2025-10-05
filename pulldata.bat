@echo off
echo ================================================================================
echo ALPHA VANTAGE DATA UPDATER
echo ================================================================================
echo.

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Check if first-time setup
if not exist database_av.db (
    echo First time setup detected. Downloading initial data...
    echo.
    python alpha_vantage_downloader.py --initial
) else (
    echo Refreshing latest data...
    echo.
    python alpha_vantage_downloader.py --refresh
)

echo.
echo ================================================================================
echo Data update complete!
echo ================================================================================
pause

@echo off
chcp 65001 >nul
setlocal ENABLEDELAYEDEXPANSION

REM -----------------------------------------------------------------
REM  migrate.bat
REM  Bundle the trading bot into migrate.zip for deployment
REM -----------------------------------------------------------------

REM Ensure we are running from the script directory
pushd "%~dp0"

set "ARCHIVE=migrate.zip"
set "STAGING=__migrate_pack"

REM Clean previous artifacts
if exist "%ARCHIVE%" del /f /q "%ARCHIVE%"
if exist "%STAGING%" rd /s /q "%STAGING%"

echo Building migration package...
mkdir "%STAGING%" || goto :error

REM -----------------------------------------------------------------
REM  Copy core directories
REM -----------------------------------------------------------------
for %%D in (bot Brains Scripts static Results) do (
  echo   [+] Copying folder %%D
  robocopy "%%~D" "%STAGING%\%%~D" /E /NFL /NDL /NJH /NJS /NP >nul
  if errorlevel 8 (
    echo   [!] robocopy reported an error for %%D
    goto :error
  )
)

REM -----------------------------------------------------------------
REM  Copy required top-level files
REM -----------------------------------------------------------------
set FILE_LIST=start.bat requirements.txt requirements_exact.txt settings.txt main.py log_manager.py ^
 alpha_vantage_downloader.py focused_optimizer.py indicators.py db_utils.py ^
 run_all_tests.py verify_consistency.py show_real_performance.py ^
 trade_history.csv Trades.log database_av.db ADDSTRATEGY.md BrainOps_Changes.md ^
 test_api_diagnostic.py fix_deployment.bat test_capitalcom_version.py check_settings_timers.py

for %%F in (%FILE_LIST%) do (
  if exist "%%~F" (
    echo   [+] Copying file %%F
    copy /Y "%%~F" "%STAGING%\%%~F" >nul
  ) else (
    echo   [!] Warning: expected file %%F not found
  )
)

REM -----------------------------------------------------------------
REM  Create archive using PowerShell Compress-Archive
REM -----------------------------------------------------------------
echo Creating %ARCHIVE% ...
powershell -NoProfile -Command "Compress-Archive -Path '%STAGING%\*' -DestinationPath '%ARCHIVE%' -Force" || goto :error

if not exist "%ARCHIVE%" goto :error

REM Clean up staging folder
rd /s /q "%STAGING%"

echo Migration archive created: %ARCHIVE%
for %%Z in (%ARCHIVE%) do echo   Size: %%~zZ bytes (%%~fZ)

echo Done.
goto :end

:error
echo.
echo [ERROR] Migration packaging failed.
if exist "%STAGING%" rd /s /q "%STAGING%"
popd
endlocal
exit /b 1

:end
popd
endlocal
exit /b 0


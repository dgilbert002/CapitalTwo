@echo off
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -q -r requirements_dip_bot.txt
echo Starting dip bot (settings.txt [DIP_BOT]; paper = true means no real orders)
".venv\Scripts\python.exe" -m bot.dip_bot
popd

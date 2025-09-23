# CapitalTwo Trading Bot

A FastAPI-based trading bot scaffold with Capital.com API integration, SQLite storage, and a simple WebSocket UI. This guide helps you run it inside a Python virtual environment on Windows.

## Prerequisites
- Python 3.10–3.12 installed and on PATH
- Git (optional)

## 1) Create and activate a virtual environment (Windows PowerShell)
```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

If execution policy blocks activation, run PowerShell as Administrator once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 2) Install dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

### TA-Lib on Windows
The project uses the `talib` module. Newer `TA-Lib` wheels are published on PyPI and should install directly on Windows for mainstream Python versions. If installation fails, install a prebuilt wheel matching your Python version, then rerun pip install:
- Download a compatible wheel from a trusted source (e.g., Christoph Gohlke’s wheels) and install:
```powershell
pip install TA_Lib‑<version>‑cp<py>‑cp<py>‑win_amd64.whl
```
Then:
```powershell
pip install -r requirements.txt
```

## 3) Configure settings
Edit `settings.txt` and set your Capital.com demo credentials under `[CREDENTIALS]`. Keep this file private.

## 4) Initialize the database (optional)
Historical data can be imported from a CSV via `import_historical_data.py`. Update the CSV path first if needed, then run:
```powershell
python import_historical_data.py
```

## 5) Run the app
```powershell
python main.py
```
Open the UI at http://localhost:8011/ (default). The WebSocket endpoint is `/ws`.

## Notes
- On Windows, the `lsof` command in `main.py` is best-effort and may no-op. If the port is busy, stop the other process or change `port` in `settings.txt`.
- Logging writes to `trading_bot.log` in the project root.


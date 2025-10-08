\
@echo off
setlocal
echo [MOEX BOT] Creating venv...
python -m venv venv
if errorlevel 1 (
  echo Failed to create venv. Ensure Python 3.10+ is installed and on PATH.
  exit /b 1
)
call venv\Scripts\activate
echo [MOEX BOT] Upgrading pip...
python -m pip install --upgrade pip
echo [MOEX BOT] Installing in editable mode...
pip install -e .
echo [MOEX BOT] Done. Activate later: venv\Scripts\activate
endlocal
pause

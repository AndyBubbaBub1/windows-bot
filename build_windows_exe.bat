@echo off
REM Build a standalone Windows executable for the MOEX bot desktop console.
REM Requires Python 3.10+, pip, and the optional "packaging" extras
REM (pip install .[packaging]).

set SCRIPT_DIR=%~dp0
pushd %SCRIPT_DIR%

python -m pip install --upgrade pip
python -m pip install .[packaging]
pyinstaller packaging\windows_desktop.spec --noconfirm

popd

echo.
echo Build complete. The executable can be found under dist\moex-bot-desktop\.

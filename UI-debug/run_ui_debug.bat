@echo off
setlocal
cd /d "%~dp0"
python ui_debug.py
if errorlevel 1 (
  echo.
  echo UI-debug did not start. Confirm Python 3.10+ includes Tkinter.
  pause
)

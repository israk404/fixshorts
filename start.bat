@echo off
cd /d "%~dp0"
title FixShorts
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
echo.
echo FixShorts stopped.
pause

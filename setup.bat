@echo off
setlocal
cd /d "%~dp0"
title FixShorts setup

echo.
echo  FixShorts setup
echo  ---------------
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo  Python isn't installed. Install Python 3.12 from https://www.python.org/downloads/windows/
  echo  and tick "Add python.exe to PATH" during the install. Then run setup.bat again.
  echo.
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  if not exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (
    echo  Installing FFmpeg with winget...
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    echo.
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo  Creating the Python environment...
  python -m venv .venv
  if errorlevel 1 (
    echo  Couldn't create the environment. Check that Python 3.11 or newer is installed.
    pause
    exit /b 1
  )
)

echo  Installing packages (a few minutes the first time)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo  Package install failed. Check your internet connection and run setup.bat again.
  pause
  exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo  Setup finished.
echo  Double-click start.bat to open FixShorts. Add your DeepSeek key in Settings.
echo  Optional: run  .venv\Scripts\python.exe setup_models.py  for the offline backup voice.
echo.
pause

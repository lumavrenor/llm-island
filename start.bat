@echo off
rem llm-island. Args go to main.py (e.g. start.bat --headless / start.bat --stub)
rem If .venv doesn't exist yet, this creates it and installs requirements.txt first (first run only).
setlocal
cd /d "%~dp0"

if exist .venv\Scripts\python.exe goto run

echo [first-time setup] .venv not found. Creating it...
set "BOOT="
rem Python 3.11 or later (tomllib)
set "VERCHK=import sys; sys.exit(sys.version_info < (3, 11))"
py -3 -c "%VERCHK%" >nul 2>&1 && set "BOOT=py -3"
if not defined BOOT python -c "%VERCHK%" >nul 2>&1 && set "BOOT=python"
if not defined BOOT (
  echo [error] No py / python command of version 3.11 or later found.
  exit /b 1
)
%BOOT% -m venv .venv || exit /b 1

echo [first-time setup] Installing dependencies ^(pip install -r requirements.txt^)...
.venv\Scripts\python.exe -m pip install -q --upgrade pip || exit /b 1
.venv\Scripts\python.exe -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo [error] pip install failed. Fix the error above, then delete .venv and run again.
  exit /b 1
)
echo [first-time setup] Done.

:run
.venv\Scripts\python.exe main.py %*
exit /b %ERRORLEVEL%

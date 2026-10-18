@echo off
rem Delete data. Next start.bat begins a new world (reset.bat --all also deletes the personas)
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe tools\reset.py %*
) else (
  python tools\reset.py %*
)

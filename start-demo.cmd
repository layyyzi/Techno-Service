@echo off
setlocal
cd /d "%~dp0"
if exist ".runtime\python\python.exe" (
    ".runtime\python\python.exe" server.py --open
    if errorlevel 1 pause
    exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 server.py --open
) else (
    python server.py --open
)
if errorlevel 1 pause

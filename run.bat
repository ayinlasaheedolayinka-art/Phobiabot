@echo off
title Telegram IPTV Scout & Auto-Poster
cd /d "%~dp0"

echo ========================================================
echo   Telegram IPTV Scout & Auto-Poster Platform
echo ========================================================
echo.

set PYTHON_CMD=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe

if not exist "%PYTHON_CMD%" (
    set PYTHON_CMD=python
)

echo Starting Scout Bot backend server...
echo Web Dashboard URL: http://localhost:8000
echo.

:: Open browser after a 2-second delay in background
start "" cmd /c "timeout /t 2 >nul & start http://localhost:8000"

:: Launch FastAPI / Uvicorn server
"%PYTHON_CMD%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

pause

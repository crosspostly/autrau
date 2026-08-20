@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM =============================================================
REM  Autrau — Telegram agent bot launcher (v1.7)
REM  Requires autrau-server already running on http://127.0.0.1:8000
REM  Set TELEGRAM_BOT_TOKEN env or telegram_bot_token in config.json
REM =============================================================

cd /d "%~dp0"

set "VENV=.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [FAIL] venv missing. Run start.bat first to create it.
    pause
    exit /b 1
)

echo.
echo ==========================================================
echo   Autrau Telegram agent bot
echo ==========================================================
echo.
echo   Talking to: http://127.0.0.1:8000
echo   Press Ctrl+C to stop.
echo.

REM --- log to file too ---
set "LOGFILE=autrau-telegram-bot.out.log"
echo. >> "%LOGFILE%"
echo [%date% %time%] -- telegram bot start -- >> "%LOGFILE%"

"%VENV_PY%" -m tools.telegram_bot >> "%LOGFILE%" 2>&1

echo.
if errorlevel 1 (
    echo ==========================================================
    echo   Bot exited with error. Check %LOGFILE%
    echo ==========================================================
    pause
    exit /b 1
)
echo Press any key to close ...
pause >nul
endlocal

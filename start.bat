@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM =============================================================
REM  Autrau — 1-click launcher
REM  - creates venv if missing
REM  - installs deps if missing
REM  - checks Python, ffmpeg, git, providers
REM  - shows a warning panel if anything is missing
REM  - starts the server, opens browser
REM =============================================================

cd /d "%~dp0"

set "VENV=.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_ACT=%VENV%\Scripts\activate.bat"

set "ERRORS=0"
set "WARNS=0"

echo.
echo ==========================================================
echo   Autrau — local multi-provider audio transcriber
echo ==========================================================
echo.

REM --- Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python not found in PATH.
    echo        Install Python 3.10+ from https://www.python.org/downloads/
    echo        IMPORTANT: tick "Add Python to PATH" during installation.
    set /a ERRORS+=1
    goto :END
)
for /f "tokens=1,2 delims=." %%a in ('python -c "import sys;print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2^>^&1') do set "PYMAJOR=%%a" & set "PYMINOR=%%b"
echo [OK]   Python %PYMAJOR%.%PYMINOR%

REM --- ffmpeg ---
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [WARN] ffmpeg not in PATH. faster-whisper needs it for mp3/m4a/ogg.
    echo        Install:  winget install Gyan.FFmpeg   (then restart terminal)
    set /a WARNS+=1
) else (
    echo [OK]   ffmpeg
)

REM --- git (for self-update) ---
where git >nul 2>&1
if errorlevel 1 (
    echo [WARN] git not in PATH. Self-update won't work; install from https://git-scm.com
    set /a WARNS+=1
) else (
    echo [OK]   git
)

REM --- venv ---
if not exist "%VENV_PY%" (
    echo.
    echo [setup] Creating venv ...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [FAIL] Could not create venv.
        set /a ERRORS+=1
        goto :END
    )
)
echo [OK]   venv

REM --- install base deps if missing ---
call "%VENV_ACT%" >nul 2>&1
"%VENV_PY%" -c "import fastapi, uvicorn, multipart" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [setup] Installing base deps ^(this may take a few minutes^) ...
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [FAIL] pip install failed.
        set /a ERRORS+=1
        goto :END
    )
)
echo [OK]   base deps

REM --- check providers ---
echo.
echo --- Providers ----------------------------------------------------
"%VENV_PY%" -c "from providers import registry; import sys; [print(f'  [{\"OK\" if p.is_available()[0] else \"--\"}] {p.info.display_name}') for p in registry.all()]" 2>nul
if errorlevel 1 (
    echo [WARN] Provider check skipped (imports failed)
    set /a WARNS+=1
)
echo -----------------------------------------------------------------

if %ERRORS% GTR 0 goto :END

REM --- optional: check for updates ---
if not "%AUTRAU_SKIP_UPDATE_CHECK%"=="1" (
    echo.
    echo [info] Checking for updates ...
    "%VENV_PY%" -m tools.update --check >nul 2>&1
    if not errorlevel 1 (
        "%VENV_PY%" -m tools.update --check 2>nul | findstr /C:"behind_by" >nul
        if not errorlevel 1 (
            echo [info] An update is available. Run update.bat to apply.
        )
    )
)

REM --- launch ---
set "AUTRAU_PORT=8000"
set "AUTRAU_HOST=127.0.0.1"

echo.
echo ==========================================================
echo   Server starting:  http://%AUTRAU_HOST%:%AUTRAU_PORT%/
echo   Press Ctrl+C to stop.
echo ==========================================================
echo.

REM Open browser after short delay
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://%AUTRAU_HOST%:%AUTRAU_PORT%/" 2>nul

REM Сервер пишет логи одновременно в консоль (здесь) и в autrau-server.out.log
"%VENV_PY%" server.py

:END
echo.
if %ERRORS% GTR 0 (
    echo ==========================================================
    echo   Setup incomplete. Fix the [FAIL] items above and retry.
    echo ==========================================================
    pause
    exit /b 1
)
echo Press any key to close ...
pause >nul
endlocal

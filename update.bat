@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM =============================================================
REM  Autrau — self-update script
REM  - pulls latest from origin (fast-forward only)
REM  - upgrades pip deps
REM  - re-checks providers
REM  - checks for model updates and prompts to download
REM =============================================================

cd /d "%~dp0"

set "VENV=.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [error] venv missing. Run start.bat first.
    pause
    exit /b 1
)

call "%VENV%\Scripts\activate.bat" >nul 2>&1

echo.
echo ==========================================================
echo   Autrau — self-update
echo ==========================================================
echo.

REM --- check if this is a git repo ---
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [skip] Not a git repository. Run publish.bat first to set up GitHub.
    goto :DEPS
)

REM --- fetch and check status ---
echo [1/4] Fetching from origin ...
git fetch --quiet origin 2>&1
if errorlevel 1 (
    echo [warn] Could not reach origin. Check network.
    goto :DEPS
)

git rev-parse --abbrev-ref --symbolic-full-name @{u} >nul 2>&1
if errorlevel 1 (
    echo [skip] No upstream tracking. Skipping pull.
    goto :DEPS
)

for /f "tokens=1,2" %%a in ('git rev-list --left-right --count HEAD...@{u}') do (
    set "AHEAD=%%a"
    set "BEHIND=%%b"
)

if "!BEHIND!"=="0" (
    echo [ok] Already up to date.
) else (
    echo [2/4] Pulling !BEHIND! new commits ...
    git pull --ff-only
    if errorlevel 1 (
        echo [fail] git pull failed. You may have local changes.
        echo        Run:  git stash ^&^& git pull ^&^& git stash pop
        pause
        exit /b 1
    )
)

:DEPS
echo.
echo [3/4] Upgrading pip deps ...
"%VENV_PY%" -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo [warn] Some deps failed to upgrade. Continuing.
)

REM --- check models ---
echo.
echo [4/4] Checking model updates ...
"%VENV_PY%" -m tools.update --check

echo.
echo ==========================================================
echo   Done.
echo   - If a new app version was pulled, RESTART the server.
echo   - To download a new model: open the UI and click
echo     "Updates" tab, or run start.bat again.
echo ==========================================================
echo.
pause
endlocal

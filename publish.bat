@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

REM =============================================================
REM  Autrau — publish to GitHub
REM  - inits local git if needed
REM  - commits all changes
REM  - creates GitHub repo `autrau` (public) via API or pushes
REM    to existing remote
REM  Usage:  publish.bat [GitHub-username] [private|public]
REM =============================================================

cd /d "%~dp0"

set "GH_USER=%~1"
if "%GH_USER%"=="" set "GH_USER=__ASK__"
set "VIS=%~2"
if "%VIS%"=="" set "VIS=public"

echo.
echo ==========================================================
echo   Autrau — publish to GitHub
echo ==========================================================
echo.

REM --- ask for username if missing ---
if "%GH_USER%"=="__ASK__" (
    set /p GH_USER="GitHub username: "
)

REM --- git config (local, repo-only) ---
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [init] Initializing git repo ...
    git init
    git config user.name "Autrau Bot"
    git config user.email "autrau-bot@local"
    git branch -M main
)

REM --- check remote ---
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    set "REPO_URL=https://github.com/%GH_USER%/autrau.git"
    echo [remote] Adding origin: !REPO_URL!
    git remote add origin !REPO_URL!
)

set "REMOTE_URL="
for /f "delims=" %%r in ('git remote get-url origin') do set "REMOTE_URL=%%r"
echo [remote] !REMOTE_URL!
echo.

REM --- add .gitignore-rendered, but check it exists ---
if not exist ".gitignore" (
    echo [error] .gitignore missing. Re-clone or create the file.
    pause
    exit /b 1
)

REM --- check for gh CLI ---
where gh >nul 2>&1
if not errorlevel 1 (
    echo [info] Using GitHub CLI to create the repo if missing ...
    gh repo view %GH_USER%/autrau >nul 2>&1
    if errorlevel 1 (
        gh repo create autrau --%VIS% --source=. --remote=origin --description "Local multi-provider audio transcriber" --push
        if not errorlevel 1 (
            echo [ok] Created and pushed to https://github.com/%GH_USER%/autrau
            goto :END
        )
        echo [warn] gh repo create failed, falling back to manual.
    )
)

REM --- manual: stage, commit, push (user creates repo on github.com) ---
echo [step 1/3] git add ...
git add -A
if errorlevel 1 (
    echo [fail] git add failed.
    pause
    exit /b 1
)

echo.
echo [step 2/3] git commit ...
git commit -m "Initial commit: Autrau v1.0.0

Multi-provider local audio transcription:
- faster-whisper (CTranslate2, default)
- whisper.cpp (via pywhispercpp)
- parakeet v3 (NVIDIA, GPU, SOTA 2025)
- Self-update via git pull
- Model updates from official HuggingFace sources
- 1-click start.bat launcher"
if errorlevel 1 (
    echo [info] Nothing to commit or commit failed.
)

echo.
echo [step 3/3] git push ...
echo.
echo ============================================================
echo  If the repo doesn't exist on GitHub yet, open this URL
echo  in your browser FIRST to create it (empty, no README):
echo.
echo     https://github.com/new?name=autrau&visibility=%VIS%
echo.
echo  Then press any key to push.
echo ============================================================
pause >nul
git push -u origin main
if errorlevel 1 (
    echo.
    echo [fail] push failed. Common causes:
    echo   - repo does not exist on GitHub
    echo   - authentication required (use a Personal Access Token)
    echo   - non-fast-forward (try: git pull --rebase)
    pause
    exit /b 1
)

echo.
echo [ok] Pushed to !REMOTE_URL!

:END
echo.
pause
endlocal

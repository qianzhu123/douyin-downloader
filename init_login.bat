@echo off
REM Douyin Downloader - Initialize / confirm login state
REM
REM Double-click to use. It will:
REM   1. Check whether douyin_profile already has a valid Douyin login (sessionid etc.)
REM   2. If valid  -> tell you it's ready, press any key to close
REM   3. If invalid -> launch a visible browser to scan-login, save the profile
REM
REM To reuse an existing profile from another project (e.g. the web project),
REM set DOUYIN_PROFILE to that folder before running, e.g.:
REM   set DOUYIN_PROFILE=D:\code\myweb\douyin\external\douyin-user-search\douyin_profile
REM Or just drop your existing "douyin_profile" folder next to this bat.
REM
REM Note: the login profile contains your Douyin account cookies and MUST NOT be
REM given to others or committed to git.

chcp 65001 >nul
setlocal
cd /d "%~dp0."

title Douyin Downloader - Login Check

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found. Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

echo.
echo ===============================================
echo   Douyin Downloader - Login State Check
echo ===============================================
echo.

python init_login.py
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo [OK] Login state is ready. You can now launch the downloader (douyin-downloader.exe ^| python app_gui.py).
) else (
    echo [FAIL] Login is not ready. Please follow the prompts above and retry.
)
echo.
pause
endlocal

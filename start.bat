@echo off
chcp 65001 >nul
setlocal

title Douyin Downloader

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] python not found
    pause
    exit /b 1
)

if not exist "%~dp0main.py" (
    echo [ERROR] main.py not found in: %~dp0
    pause
    exit /b 1
)

echo.
echo   ================================
echo    Douyin Video/Image Downloader
echo   ================================
echo.
echo   1. Paste URL or share text
echo   2. Enter a file path with URLs
echo.

set "MODE="
set /p MODE=Choose mode [1=URL, 2=File]:

if "%MODE%"=="2" goto input_file

:input_url
set "DOUYIN_URL="
set /p DOUYIN_URL=Paste Douyin link or share text:
if "%DOUYIN_URL%"=="" (
    echo [ERROR] Input cannot be empty
    echo.
    goto input_url
)
set "CMD_ARGS=%DOUYIN_URL%"
goto input_output

:input_file
set "URL_FILE="
set /p URL_FILE=Enter file path with URLs:
if "%URL_FILE%"=="" (
    echo [ERROR] File path cannot be empty
    echo.
    goto input_file
)
set "CMD_ARGS=-f %URL_FILE%"

:input_output
set "OUTPUT_DIR="
set /p OUTPUT_DIR=Save to [Enter for default: .\downloads]:
if "%OUTPUT_DIR%"=="" set "OUTPUT_DIR=.\downloads"

echo.
echo [INFO] Save:   %OUTPUT_DIR%
echo [INFO] Downloading, please wait...
echo.

python "%~dp0main.py" %CMD_ARGS% -o "%OUTPUT_DIR%"

if errorlevel 1 (
    echo.
    echo [ERROR] Download failed
) else (
    echo.
    echo [OK] Download completed
)

endlocal
pause

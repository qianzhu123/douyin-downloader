@echo off
chcp 65001 >nul
REM douyin-downloader - PyInstaller build script (onefile GUI)
setlocal
cd /d "%~dp0."
set "PY=python"
set "APP_NAME=抖音下载器"

echo [1/3] 确保 app_icon.ico 存在...
if not exist "app_icon.ico" (
    echo [*] 生成图标...
    "%PY%" make_icon.py || (echo [x] 图标生成失败 & exit /b 1)
)

echo [2/3] 清理旧产物...
if exist "dist\%APP_NAME%.exe" del /q "dist\%APP_NAME%.exe"
if exist "build\抖音下载器" rmdir /s /q "build\抖音下载器"

echo [3/3] PyInstaller 构建 onefile (含图标)...
"%PY%" -m PyInstaller --noconfirm --clean "抖音下载器.spec"

if exist "dist\%APP_NAME%.exe" (
    echo.
    echo Build complete: dist\%APP_NAME%.exe
) else (
    echo.
    echo Build failed. Review the output above.
    exit /b 1
)
endlocal

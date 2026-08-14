@echo off
chcp 65001 >nul
REM douyin-downloader - PyInstaller build script (onefile GUI)
setlocal
cd /d "%~dp0."
REM conda base 的 Python 3.13 会让 PyInstaller 6.x 在 Analysis 阶段僵死
REM (CPU 0、日志停在 "Analyzing modules for base_library.zip")。
REM 必须用 Python 3.11 打包(实测 conda auto 环境 OK)。优先级:
REM   1) PYTHON_BUILD env 变量(用户显式指定解释器)
REM   2) conda auto 环境(3.11.15)
REM   3) PATH 上的 python(可能仍是 13，会死锁——仅作最后兜底并警告)
set "PY="
if defined PYTHON_BUILD (
    set "PY=%PYTHON_BUILD%"
    echo [*] 使用 PYTHON_BUILD=%PYTHON_BUILD%
) else (
    set "CONDA_AUTO=D:\tools\Dev\Runtime\Anaconda\envs\auto\python.exe"
    if exist "%CONDA_AUTO%" (
        set "PY=%CONDA_AUTO%"
        echo [*] 使用 conda auto (Python 3.11) 解释器打包
    ) else (
        echo [!] 未找到 conda auto 环境，回退 PATH 上的 python(若是 3.13 会卡死!)
        set "PY=python"
    )
)
"%PY%" --version 2>nul || (echo [x] 无可用 Python 解释器 & exit /b 1)
set "APP_NAME=抖音下载器"

echo [1/3] 确保 assets\app_icon.ico 存在...
if not exist "assets\app_icon.ico" (
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

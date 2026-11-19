@echo off
chcp 936 >nul
REM douyin-downloader - PyInstaller build script (onefile GUI)
setlocal
cd /d "%~dp0."
REM conda base 的 Python 3.13 会让 PyInstaller 6.x 在 Analysis 阶段僵死
REM (CPU 0、日志停在 "Analyzing modules for base_library.zip")。
REM 必须用 Python 3.11 打包。原 conda auto 环境已删,现用项目内 uv venv。
REM 注意: cmd 在 if(...) 括号块内 %var% 为进入块前展开,故探测逻辑全部用 goto 流程,不用块内变量。
set "PY="
if defined PYTHON_BUILD (
    set "PY=%PYTHON_BUILD%"
    goto have_py
)
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
    set "PY=%VENV_PY%"
    goto have_py
)
echo [!] 未找到项目内 .venv, 请先运行: uv venv --python 3.11 然后 uv pip install pyinstaller
echo [!] 回退 PATH 上的 python, 若是 3.13 会卡死
set "PY=python"
:have_py
"%PY%" --version 2>nul || (echo [x] 无可用 Python 解释器 & exit /b 1)
set "APP_NAME=抖音下载器"

echo [1/3] 确保 assets\app_icon.ico 存在
if not exist "assets\app_icon.ico" (
    echo [*] 生成图标
    "%PY%" make_icon.py || (echo [x] 图标生成失败 & exit /b 1)
)

echo [2/3] 清理旧产物
if exist "dist\%APP_NAME%.exe" del /q "dist\%APP_NAME%.exe"
if exist "build\抖音下载器" rmdir /s /q "build\抖音下载器"

echo [3/3] PyInstaller 构建 onefile, 含图标
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

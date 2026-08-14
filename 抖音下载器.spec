# -*- mode: python ; coding: utf-8 -*-
"""抖音下载器 - PyInstaller spec (onefile, noconsole, 含图标 + chromium 自检)。

构建: build.bat
"""
from PyInstaller.utils.hooks import collect_all

datas = [
    ('assets/app_icon.ico', 'assets'),
]
binaries = []
hiddenimports = [
    'httpx',
    'downloader',
]

# 注意：不再 collect_all('playwright')。那是 PyInstaller 在 Anaconda-Python3.13
# 上卡死几十分钟的根由(playwright 的 node 驱动含几千小文件，collect 扫描极慢/死循环)。
# 改为运行时由 app_gui 动态把本机 site-packages 中的 playwright 插到 sys.path 前，
# 复用本机已装的 playwright 驱动 + 本机 chromium(见 init_login._use_system_playwright)。
# 代价：exe 仅在本机(已装 python+playwright)可跑 —— 对本机小工具可接受。

# 仍把 init_login 显式收进来(GUI 调它)。
hiddenimports += ['init_login']

a = Analysis(
    ['app_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除会卡死的全部 playwright 收集；运行时走本机 site-packages。
        'playwright', 'playwright.sync_api', 'playwright.async_api',
        'playwright._impl', 'playwright._impl.__main__',
        # 只用 PyQt5，排除其它 Qt 绑定(否则 PyInstaller 报多 Qt 冲突)
        'PySide6', 'PySide2', 'PyQt6', 'PyQt4',
        # 体积瘦身
        'matplotlib', 'numpy', 'pandas', 'IPython', 'jedi', 'parso',
        'black', 'yapf_third_party', 'astroid', 'pygments', 'sphinx',
        'docutils', 'babel', 'rich', 'zmq', 'nbformat', 'jsonschema',
        'tkinter', 'matplotlib.backends', 'PIL.Image', 'cryptography',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='抖音下载器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app_icon.ico',
)

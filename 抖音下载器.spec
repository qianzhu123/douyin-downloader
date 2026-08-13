# -*- mode: python ; coding: utf-8 -*-
"""抖音下载器 - PyInstaller spec (onefile, noconsole, 含图标 + chromium 自检)。

构建: build.bat
"""
from PyInstaller.utils.hooks import collect_all

datas = [
    ('app_icon.ico', '.'),
]
binaries = []
hiddenimports = [
    'httpx',
    'playwright',
    'playwright.sync_api',
    'downloader',
]

# 把 playwright 的 python 资源(驱动、node 等)全收进来；运行时首启再装 chromium
pw = collect_all('playwright')
datas += pw[0]
binaries += pw[1]
hiddenimports += pw[2]

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
        # 只用 PyQt5，排除其它 Qt 绑定(否则 PyInstaller 报多 Qt 冲突)
        'PySide6', 'PySide2', 'PyQt6', 'PyQt4',
        # 体积瘦身：用不到的重量级包
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
    icon='app_icon.ico',
)

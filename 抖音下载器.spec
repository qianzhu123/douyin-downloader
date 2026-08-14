# -*- mode: python ; coding: utf-8 -*-
"""抖音下载器 - PyInstaller spec (onefile, noconsole, 含图标 + chromium 自检)。

构建: build.bat
"""
from PyInstaller.utils.hooks import collect_all
import sysconfig
from pathlib import Path

# ── 烙印打包机真实 site-packages 到 runtime hook(在 Analysis 之前填充) ──
# exe 启动最早期执行该 hook，把本机 site-packages 插 sys.path 前，使 excludes 掉的
# playwright 能运行时从本机已装处 import。详见 _runtime_hook.py 模板注释。
# 源码模板 _runtime_hook.py 用 {SITEPACKAGES} 占位保持干净(不被提交污染)；这里
# 用打包机 sysconfig 探测的真实 site-packages 替换占位，写到 _runtime_hook_filled.py
# (临时产物，gitignore 覆盖)，runtime_hooks 指它。
_SITEPKGS = sysconfig.get_paths().get("purelib", "")
_tmpl = Path("_runtime_hook.py").read_text(encoding="utf-8")
_filled_path = Path("_runtime_hook_filled.py")
_filled_path.write_text(_tmpl.replace("{SITEPACKAGES}", _SITEPKGS), encoding="utf-8")
_SPECDIR = Path(SPECPATH) if "SPECPATH" in dir() else Path(".")
RUNTIME_HOOK = str((_SPECDIR / "_runtime_hook_filled.py").resolve())

datas = [
    ('assets/app_icon.ico', 'assets'),
]
binaries = []
# 模块已收进 src/ 包：必须把 src 及其子模块显式列进 hiddenimports，
# 否则 onefile 在运行时 import 不到包(App虚树)。httpx 同理显式列。
hiddenimports = [
    'httpx',
    'src',
    'src.downloader',
    'src.init_login',
    'src.paths',
]

# 注意：不再 collect_all('playwright')。那是 PyInstaller 在 Anaconda-Python3.13
# 上卡死几十分钟的根由(playwright 的 node 驱动含几千小文件，collect 扫描极慢/死循环)。
# 改为运行时由 app_gui 动态把本机 site-packages 中的 playwright 插到 sys.path 前，
# 复用本机已装的 playwright 驱动 + 本机 chromium(见 init_login._use_system_playwright)。
# 代价：exe 仅在本机(已装 python+playwright)可跑 —— 对本机小工具可接受。

# (旧 hiddenimports += ['init_login'] 已删：init_login 已挪进 src/，
#  上方 hiddenimports 里已列 'src'/'src.init_login'/'src.paths'/'src.downloader'。)

a = Analysis(
    ['app_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[RUNTIME_HOOK],
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

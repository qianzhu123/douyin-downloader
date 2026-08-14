"""douyin-downloader 公共路径解析(运行时推导，不写死绝对路径)。

原则：
- 默认下载目录优先用户家目录下的 Downloads(跨用户、跨机器都对)；
  找不到该目录则回退到本项目根的 downloads/(用 sys.executable 或 __file__ 推导，
  确保脚本态与 PyInstaller 打包态都能落到正确位置，不被 _MEIPASS 临时目录坑)。
- 全程用 pathlib + 环境变量/Home 推导，绝不硬编码本机盘符路径。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    """程序根目录(放 downloads/profile 等用户数据的稳定位置)。

    - PyInstaller onefile 打包后 __file__ 在临时解包目录(_MEIPASS)，不能放持久数据；
      用 sys.executable 父目录(即 dist/抖音下载器.exe 旁)。
    - 脚本直跑时回退 __file__ 父目录(脚本同级)。
    """
    exe = getattr(sys, "executable", "") or ""
    if getattr(sys, "frozen", False) and exe:
        return Path(exe).resolve().parent
    return Path(__file__).resolve().parent


def default_download_dir() -> Path:
    """默认下载目录：优先 ~/Downloads，不存在则回退项目内 downloads/。

    返回的目录保证已存在(makedirs)；语义上=用户系统的"下载"文件夹，
    跟着当前用户家目录走，不同用户、不同机器都能正确指向其各自的下载位置。
    """
    home = Path.home()
    cand = home / "Downloads"
    if cand.exists() and cand.is_dir():
        return cand
    # 某些中文系统/非标准布局：尝试用户文档库/桌面 Downloads 也常见，但最稳即上面。
    fallback = project_root() / "downloads"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback

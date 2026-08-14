# -*- coding: utf-8 -*-
"""抖音下载器 打包 runtime hook(构建期自动生成)。

由 spec 在 PyInstaller Analysis 之前生成，把"打包机当前解释器的真实 site-packages"
烙进此文件。exe 启动最早期(任何 app 代码 import 之前)执行本 hook，将真实 site-packages
插到 sys.path 最前，使 excludes 掉的 `playwright` 在运行时能从本机已装处 import。

为何需要：PyInstaller 打包后 exe 的 sys.path 里没有真实 site-packages(_MEIPASS 取而代之)，
而 `init_login._use_system_playwright` 的探测依赖 sys.path/site-packages，exe 里全落空
→ `from playwright...` 崩 ModuleNotFoundError。本 hook 在探测之前就把真实 site-packages
灌进 sys.path，让 _use_system_playwright 能命中本机 playwright。

代价：烙进去的是**打包机**的 site-packages 绝对路径，故 exe 仅在该机可跑(与项目既定
"仅本机可用"前提一致)。换机重打会自动烙成新机的 site-packages，无需手改。
"""
import os as _os
import sys as _sys

_SITEPACKAGES = r"{SITEPACKAGES}"

# 仅当烙进去的 site-packages 在本机真实存在时才插(换机/误拷时安全退化，不破坏启动)
if _os.path.isdir(_SITEPACKAGES) and _SITEPACKAGES not in _sys.path:
    _sys.path.insert(0, _SITEPACKAGES)

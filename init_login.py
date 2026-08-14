"""初始化/复用抖音登录态 profile。

用法:
    python init_login.py            # 检测现有 profile；无效则弹浏览器扫码登录
    python init_login.py --force    # 强制重新登录(覆盖现有 profile)
    python init_login.py --status   # 只检测状态，不登录

profile 默认落在脚本同级目录的 `douyin_profile/`，供 downloader 与 GUI 复用。
登录态有效时，downloader 能拿到喜欢列表/私密等需要登录的直链。
"""
import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _ensure_stdio_for_frozen():
    """无控制台的 PyInstaller windowed 程序里 stdio 为 None，playwright 的 node
    驱动子进程拿不到有效 stdio 会启动失败/卡住。这里把它重定向到程序目录下的日志文件，
    让子进程有可用的 stdin/stdout/stderr。幂等可多次调用。
    """
    try:
        if sys.stdout is not None and sys.stderr is not None and sys.stdin is not None:
            return None
    except Exception:
        pass
    try:
        log_path = _frozen_dir() / "gui_stdio.log"
        f = open(str(log_path), "a", encoding="utf-8")
        class _Tee:
            def __init__(s, base): s.base = base
            def write(s, t):
                try: f.write(t); f.flush()
                except Exception: pass
                if s.base is not None:
                    try: s.base.write(t)
                    except Exception: pass
            def flush(s):
                try: f.flush()
                except Exception: pass
                if s.base is not None:
                    try: s.base.flush()
                    except Exception: pass
        if sys.stdout is None: sys.stdout = _Tee(None)
        if sys.stderr is None: sys.stderr = _Tee(None)
        if sys.stdin is None:
            sys.stdin = open(os.devnull, "r")
        return str(log_path)
    except Exception:
        return None


def _point_to_system_chromium():
    """让 playwright 去系统浏览器缓存找 chromium，而非 PyInstaller 临时解包目录里
    (空)的 .local-browsers。

    原因：spec 用 collect_all('playwright') 收集的是 playwright 的 python/node 驱动，
    不含 ~150MB 的 chromium 内核；collect_all 会把 .local-browsers 目录也打进 _MEIPASS，
    但里面没有 chrome.exe，于是 exe 运行时报
    "Executable doesn't exist at _MEIPASS/.../.local-browsers/chromium-XXXX/...".

    修法：在 import playwright 之前设 PLAYWRIGHT_BROWSERS_PATH 指向系统
    %LocalAppData%\ms-playwright(脚本态 playwright install chromium 装在那)，
    这样 exe 复用系统已装的 chromium，无需把内核打包进 exe。
    幂等，可多次调用；不硬编码本机绝对路径——用环境变量运行时推导。
    """
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return  # 已显式指定，尊重之
    # 优先 %LocalAppData%\ms-playwright(Windows 默认)，回退 ~\.cache\ms-playwright
    for var in ("LocalAppData", "AppData"):
        base = os.environ.get(var)
        if base:
            cand = Path(base) / "ms-playwright"
            if cand.exists():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(cand)
                return
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if home:
        cand = Path(home) / ".cache" / "ms-playwright"
        if cand.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(cand)


def _use_system_playwright():
    """让打包后的 exe 复用本机已装的 playwright(驱动 + chromium)。

    spec 去 collect_all('playwright') 后，exe 里不含 playwright 包；
    这里在 import playwright 之前把本机 site-packages 插到 sys.path 前，
    使 `from playwright...` 能命中本机已装的那个。

    探测顺序(运行时推导，无硬编码绝对路径)：
      1) 任意已 import 模块 __file__ 所在的解释器 site-packages(xs，开发态自然命中)
      2) sys.sitepackages
      3) sys.prefix / site-packages、sys.base_prefix / site-packages
      4) %LocalAppData%\\..\\..\\site-packages 兜底一般用不到
    命中标准：候选目录下存在 playwright/__init__.py。
    幂等，仅当 sys.path 里尚未命中时才插。
    """
    import sys as _sys
    # 已能 import 就不必动
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        pass

    cands = []
    for m in list(_sys.modules.values()):
        f = getattr(m, "__file__", None)
        if f and "site-packages" in f:
            sp = Path(f).resolve()
            # 回退到 site-packages 根
            parts = sp.parts
            if "site-packages" in parts:
                i = parts.index("site-packages")
                cands.append(Path(*parts[: i + 1]))
    for sp in getattr(_sys, "path", []):
        if sp and "site-packages" in sp:
            cands.append(Path(sp))
    for base in (_sys.prefix, _sys.base_prefix):
        cands.append(Path(base) / "Lib" / "site-packages")
    cands.append(Path(_sys.base_prefix) / "site-packages")
    for c in cands:
        try:
            c = c.resolve()
        except Exception:
            continue
        if (c / "playwright" / "__init__.py").exists():
            s = str(c)
            if s not in _sys.path:
                _sys.path.insert(0, s)
            return True
    return False


def _frozen_dir() -> Path:
    """运行时推导的"程序根目录"。

    - PyInstaller onefile 打包后 __file__ 指向临时解包目录(_MEIPASS)，
      那里每次启动都会变、并随进程退出销毁，**不能**放持久 profile。
      sys.executable 才是真实 exe 路径(dist/抖音下载器.exe)，
      其父目录即用户视角的"程序目录"，profile 应落这里。
    - 脚本直跑(开发态)时 sys.executable 是 python.exe，
      退回 __file__ 所在目录(脚本同级)。
    全程不硬编码任何绝对路径，跟随实际部署位置走。
    """
    import sys
    exe = getattr(sys, "executable", "")
    if not exe:
        return SCRIPT_DIR
    exe_p = Path(exe).resolve()
    # frozen 才走 exe 目录；脚本态 exe 是 python 解释器，回退脚本目录。
    if getattr(sys, "frozen", False):
        return exe_p.parent
    # 脚本直跑：解释器通常在别处，仍用脚本目录
    return SCRIPT_DIR


DEFAULT_PROFILE = None  # 懒构造，避免 import 期固定死

COOKIES_DB_RELS = [
    "Default/Network/Cookies",
    "Default/Cookies",
]


def profile_path() -> Path:
    """解析要用的 profile 路径。优先环境变量 DOUYIN_PROFILE，否则程序根目录下 douyin_profile。

    profile 固定落在"程序根目录"(exe 旁或脚本旁)的 douyin_profile/，
    而非 PyInstaller 临时解包目录——后者每次启动都变、无法持久化登录态。
    """
    env = os.environ.get("DOUYIN_PROFILE", "").strip()
    if env:
        return Path(env)
    return _frozen_dir() / "douyin_profile"


def _cookies_db(profile: Path) -> Path | None:
    for rel in COOKIES_DB_RELS:
        p = profile / rel
        if p.exists():
            return p
    return None


def check_login(profile: Path) -> tuple[bool, str]:
    """检测 profile 是否含有效抖音登录 cookie(sessionid 等)。

    返回 (有效, 说明)。
    """
    if not profile.exists():
        return False, f"profile 目录不存在: {profile}"
    db = _cookies_db(profile)
    if not db:
        return False, f"profile 内未找到 Cookies 库(可能不是完整 chromium profile)"
    if not _is_unlocked(profile):
        # SingletonLock 常因上次异常退出残留(非真占用)。先尝试清陈旧锁，再判 cookies，
        # 避免把"残留锁"误报成"登录态丢失"。
        if not _try_clear_stale_lock(profile):
            return False, "profile 被其它进程锁定(GUI/downloader 还开着?)，请先关掉再用"
    try:
        conn = sqlite3.connect(str(db))
        rows = conn.execute(
            'SELECT name FROM cookies WHERE host_key LIKE "%douyin%"'
        ).fetchall()
        conn.close()
    except Exception as e:
        return False, f"读取 Cookies 失败: {e}"
    names = {r[0] for r in rows}
    key = {"sessionid", "sessionid_ss", "sid_guard"}
    hit = key & names
    if hit:
        return True, f"已登录(关键cookie: {sorted(hit)})"
    return False, "未发现 sessionid/sid_guard 等登录态 cookie，需重新登录"


def _is_unlocked(profile: Path) -> bool:
    for lock in (profile / "SingletonLock", profile / "Default" / "SingletonLock"):
        if lock.exists():
            return False
    return True


def _try_clear_stale_lock(profile: Path) -> bool:
    """尝试清掉残留的 SingletonLock。真有其它进程占用时链接无法删 -> 返回 False。"""
    import os as _os
    for lock in (profile / "SingletonLock", profile / "Default" / "SingletonLock"):
        if not lock.exists():
            continue
        try:
            # SingletonLock 多为符号链接(os.unlink 解链而非删目标)。
            if lock.is_symlink():
                lock.unlink()
            else:
                lock.unlink()
        except OSError:
            # 锁被活动进程占用，删不掉 -> 真占用。
            return False
    return True


def login_interactive(profile: Path, *, headless: bool = False,
                       timeout_sec: int = 300, on_progress=None,
                       block_console: bool = True) -> bool:
    """弹出一个有头 chromium 让用户扫码登录抖音，登录成功后固化 profile。

    登录成功判定: cookies 出现 sessionid/sid_guard。
    - headless: True 时不弹窗(仅用于无显示环境兜底/自检，扫码需有头)。
    - timeout_sec: 自动检测登录的最长等待。
    - on_progress(msg): 可选回调，GUI 用来把进度推到日志(替代 print 阻塞)。
    - block_console: 末尾是否 input() 等回车。GUI/无控制台调用应传 False。

    返回 True 表示检测到登录成功。
    """
    def _log(s):
        print(s)
        if on_progress:
            try: on_progress(s)
            except Exception: pass

    _ensure_stdio_for_frozen()
    _point_to_system_chromium()
    _use_system_playwright()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _log("[ERROR] 未安装 playwright")
        return False
    except Exception as e:
        _log(f"[ERROR] 初始化 playwright 失败: {e}")
        return False

    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)
    profile.mkdir(parents=True, exist_ok=True)

    _log(f"[*] 启动浏览器用于登录，profile 将写入: {profile}")
    if not headless:
        _log("[*] 请在弹出的窗口中扫码登录抖音(https://www.douyin.com)")

    try:
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(profile),
                headless=headless,
                viewport={"width": 1280, "height": 800},
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=30000)

            logged = False
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                page.wait_for_timeout(2000)
                ok, _ = check_login(profile)
                if ok:
                    logged = True
                    _log("[+] 检测到登录成功(sessionid 已写入)")
                    break
            if not logged:
                _log(f"[!] {timeout_sec} 秒内未检测到登录。")
            if block_console:
                try:
                    input()
                except EOFError:
                    pass
            ctx.close()
    except Exception as e:
        _log(f"[x] 浏览器启动/登录异常: {e}")
        try:
            import traceback as _tb
            (_frozen_dir() / "login_error.log").write_text(
                _tb.format_exc(), encoding="utf-8")
        except Exception:
            pass
        return False
    if logged:
        ok, msg = check_login(profile)
        _log(f"[+] 最终状态: {msg}")
        return ok
    return False


def main():
    ap = argparse.ArgumentParser(description="抖音下载器 - 初始化/复用登录态")
    ap.add_argument("--force", action="store_true", help="强制重新登录(覆盖现有 profile)")
    ap.add_argument("--status", action="store_true", help="只检测状态不登录")
    ap.add_argument("--profile", default="", help="指定 profile 路径(默认 ./douyin_profile)")
    args = ap.parse_args()

    if args.profile:
        os.environ["DOUYIN_PROFILE"] = args.profile
    prof = profile_path()

    ok, msg = check_login(prof)
    print(f"[*] profile: {prof}")
    print(f"[*] 状态: {msg}")

    if args.status:
        sys.exit(0 if ok else 1)

    if ok and not args.force:
        print("[+] 登录态有效，可直接使用 GUI / downloader。")
        sys.exit(0)

    if ok and args.force:
        print("[*] --force: 重新登录(覆盖现有 profile)...")

    if os.environ.get("DOUYIN_PROFILE", "").strip():
        # 指定了外部 profile(比如复用 myweb 的)
        print(f"[!] 指定 DOUYIN_PROFILE={prof} 未登录或无效。")
        print("    若是复用其它项目的 profile，请在那里先登录好再复用；或用 --force 在此路径重新登录。")
    if not login_interactive(prof):
        print("[x] 登录未完成。")
        sys.exit(1)
    print("[+] 登录态已就绪。")


if __name__ == "__main__":
    main()

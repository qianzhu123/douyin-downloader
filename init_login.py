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
DEFAULT_PROFILE = SCRIPT_DIR / "douyin_profile"
COOKIES_DB_RELS = [
    "Default/Network/Cookies",
    "Default/Cookies",
]


def profile_path() -> Path:
    """解析要用的 profile 路径。优先环境变量 DOUYIN_PROFILE，否则默认 profile。"""
    env = os.environ.get("DOUYIN_PROFILE", "").strip()
    if env:
        return Path(env)
    return DEFAULT_PROFILE


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
        return False, "profile 被其它进程锁定(常驻 Chrome 正在用?)，请先关掉再用"
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


def login_interactive(profile: Path) -> bool:
    """弹出一个有头 chromium 让用户扫码登录抖音，登录成功后固化 profile。

    登录成功判定: 抖音首页出现登录用户头像/昵称，或 cookies 出现 sessionid。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] 未安装 playwright，先: pip install playwright && playwright install chromium")
        return False

    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)
    profile.mkdir(parents=True, exist_ok=True)

    print(f"[*] 启动有头浏览器用于登录，profile 将写入: {profile}")
    print("[*] 请在弹出的窗口中扫码登录抖音(https://www.douyin.com)")
    print("[*] 登录成功后回到这里回车，或等待自动检测(最多 5 分钟)")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.douyin.com", wait_until="domcontentloaded", timeout=30000)

        logged = False
        deadline = time.time() + 300
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            ok, _ = check_login(profile)
            if ok:
                logged = True
                print("[+] 检测到登录成功(sessionid 已写入)")
                break
        if not logged:
            print("[!] 5 分钟内未检测到登录，将保留当前窗口，可继续登录；按回车结束")
        try:
            input()
        except EOFError:
            pass
        ctx.close()
    if logged:
        ok, msg = check_login(profile)
        print(f"[+] 最终状态: {msg}")
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

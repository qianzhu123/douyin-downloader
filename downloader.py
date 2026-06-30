"""抖音无水印视频/图集下载器 -- 核心下载逻辑"""

import json
import re
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright


def _print(msg: str):
    """安全输出，解决 Windows 控制台编码问题"""
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), flush=True)


def _sanitize_filename(title: str) -> str:
    """清理文件名中的非法字符"""
    title = re.sub(r'[<>:"/\\|?*]', '', title)
    title = title.strip().strip('.')
    if len(title) > 100:
        title = title[:100]
    if not title:
        title = f"douyin_{int(time.time())}"
    return title


def _extract_content_type(page) -> str:
    """
    判断当前页面是视频还是图集。
    返回: "video" | "image" | "unknown"
    """
    return page.evaluate("""() => {
        const url = window.location.href;
        if (/\\/note\\//.test(url)) return 'image';
        if (/\\/video\\//.test(url)) return 'video';

        const video = document.querySelector('video');
        if (video) {
            const src = video.currentSrc || video.src || '';
            if (src.includes('.mp3') || src.includes('ies-music')) return 'image';
            if (src.includes('douyinvod') || src.includes('.mp4')) return 'video';
        }
        return 'unknown';
    }""")


def _extract_video_info(page) -> dict:
    """从视频页面提取视频直链、标题、作者"""
    return page.evaluate("""() => {
        const video = document.querySelector('video');
        const src = video ? (video.currentSrc || video.src) : '';

        const titleEl =
            document.querySelector('h1') ||
            document.querySelector('[data-e2e="video-title"]') ||
            document.querySelector('[class*="title"]');
        const title = titleEl ? titleEl.textContent.trim() : '';

        const authorEl =
            document.querySelector('[data-e2e="video-nickname"]') ||
            document.querySelector('[class*="author"] [class*="name"]');
        const author = authorEl ? authorEl.textContent.trim() : '';

        return { type: 'video', video_url: src, title, author };
    }""")


def _scroll_and_collect_images(page, max_presses: int = 80) -> list[str]:
    """
    通过 Playwright 键盘操作逐张翻看图集，触发懒加载，
    然后从 DOM img 标签中收集所有图集内容图片 URL。
    使用 img.src 是因为这些 URL 已经包含完整的签名参数。
    """
    _print("[*] 正在逐张浏览图集以加载所有图片...")

    total_images = page.evaluate("""() => {
        const allText = document.body.innerText;
        const match = allText.match(/\\b(\\d+)\\s*\\/\\s*(\\d+)\\b/);
        if (match) return parseInt(match[2]);
        return 0;
    }""")

    if total_images:
        _print(f"[+] 检测到图集共 {total_images} 张")

    # 初始化收集容器
    # 匹配 aweme-images 和 aweme-images-v2 以及 aweme_images
    page.evaluate("""() => {
        window.__imgUrls = new Set();
        function collect() {
            document.querySelectorAll('img').forEach(img => {
                const src = img.src || '';
                if (src.includes('aweme-image') || src.includes('aweme_images')) {
                    window.__imgUrls.add(src);
                }
            });
        }
        collect();
        window.__collectImages = collect;
    }""")

    prev_count = page.evaluate("() => window.__imgUrls.size")
    stagnant = 0

    for i in range(max_presses):
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(400)

        page.evaluate("() => window.__collectImages()")
        current = page.evaluate("() => window.__imgUrls.size")

        if current == prev_count:
            stagnant += 1
            if stagnant >= 8:
                break
        else:
            stagnant = 0
            _print(f"  已加载 {current} 张...")

        prev_count = current

        if total_images and current >= total_images:
            break

    # 最终收集 + 去重（同一图片的不同尺寸 URL 要去重，以 ~  和 ? 之间的内容为 key）
    image_urls = page.evaluate("""() => {
        window.__collectImages();
        // 去重：按照图片标识符去重，保留高质量版本
        const byKey = {};
        for (const url of window.__imgUrls) {
            // 提取图片标识符: ~ 之前的部分 + ~ 到 : 之间的模板名
            const key = url.replace(/~[^:]*/, '').replace(/\\?.*/, '');
            if (!byKey[key] || url.includes('aweme-images-v2:300') || url.includes('aweme-images:q75')) {
                byKey[key] = url;
            }
        }
        return Object.values(byKey);
    }""")

    return image_urls if image_urls else []


def _download_image_via_playwright(page, url: str, output_path: Path) -> int:
    """
    通过 Playwright 的 page.route 拦截图片请求，在浏览器上下文中获取图片。
    然后用 page.request (属于浏览器上下文的 API 请求) 下载，自动携带 cookies。
    """
    # 使用 Playwright 的 browser-context request API
    # 这个 API 会自动带有当前 context 的 cookies 和正确的 Origin
    resp = page.request.get(url)

    if not resp.ok:
        raise RuntimeError(f"浏览器 API 下载图片失败: {resp.status} {resp.status_text}")

    body = resp.body()
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_bytes(body)
    if output_path.exists():
        output_path.unlink()
    tmp_path.rename(output_path)

    return len(body)


def _extract_image_title_author(page) -> dict:
    """从图集页面提取标题和作者"""
    return page.evaluate("""() => {
        const titleEl =
            document.querySelector('h1') ||
            document.querySelector('[data-e2e="video-title"]') ||
            document.querySelector('[class*="title"]');
        const title = titleEl ? titleEl.textContent.trim() : '';

        const authorEl =
            document.querySelector('[data-e2e="video-nickname"]') ||
            document.querySelector('[class*="author"] [class*="name"]');
        const author = authorEl ? authorEl.textContent.trim() : '';

        return { title, author };
    }""")


def _download_file(url: str, output_path: Path, max_retries: int = 2) -> int:
    """下载文件（视频），返回文件大小（字节）"""
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "identity;q=1, *;q=0",
        "Origin": "https://www.douyin.com",
        "Referer": "https://www.douyin.com/",
        "Range": "bytes=0-",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/146.0.0.0 Safari/537.36"
        ),
    }

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            with httpx.stream(
                "GET", url, headers=headers, timeout=60, follow_redirects=True
            ) as response:
                response.raise_for_status()
                tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
                total = 0
                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        total += len(chunk)
                if output_path.exists():
                    output_path.unlink()
                tmp_path.rename(output_path)
                return total
        except (httpx.HTTPStatusError, httpx.TransportError) as e:
            last_error = e
            if attempt < max_retries:
                _print(f"  [!] 下载失败，第 {attempt + 1} 次重试...")
                time.sleep(1)

    raise RuntimeError(f"下载失败（已重试 {max_retries} 次）: {last_error}")


def download_douyin(url: str, output_dir: str = "") -> dict:
    """
    下载抖音无水印视频或图集

    Args:
        url: 抖音链接（支持视频、图文笔记的短链接和完整链接）
        output_dir: 输出目录，默认为脚本所在目录的 downloads 子文件夹

    Returns:
        dict: 下载结果
    """
    # Determine output directory (relative to current working directory)
    if not output_dir:
        output_dir = str(Path.cwd() / "downloads")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    _print("[*] 正在启动浏览器...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            _print(f"[*] 正在访问: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=20000)

            _print("[*] 等待页面加载...")
            try:
                page.wait_for_selector(
                    "video, h1, [data-e2e='video-title'], [class*='note']",
                    timeout=15000,
                )
            except Exception:
                pass

            page.wait_for_timeout(2000)

            # ── 判断内容类型 ──
            content_type = _extract_content_type(page)

            if content_type == "video":
                # ══════ 视频下载 ══════
                info = _extract_video_info(page)
                video_url = info.get("video_url", "")
                title = info.get("title", "")
                author = info.get("author", "")

                if not video_url or "douyinvod" not in video_url:
                    raise RuntimeError("未能提取到有效的视频地址")

                _print(f"[+] 类型: 视频")
                _print(f"[+] 标题: {title}")
                if author:
                    _print(f"[+] 作者: {author}")

                filename = _sanitize_filename(title) + ".mp4"
                file_path = output_path / filename

                _print("[*] 正在下载视频...")
                file_size = _download_file(video_url, file_path)

                return {
                    "type": "video",
                    "title": title,
                    "author": author,
                    "file_path": str(file_path),
                    "file_size": file_size,
                }

            elif content_type == "image":
                # ══════ 图集下载 ══════
                # 滚动收集：先翻看所有图片让浏览器加载，再从 img.src 提取完整 URL
                image_urls = _scroll_and_collect_images(page)

                if not image_urls:
                    raise RuntimeError("未能从页面中提取到图片地址")

                info = _extract_image_title_author(page)
                title = info.get("title", "")
                author = info.get("author", "")

                _print(f"[+] 类型: 图集 ({len(image_urls)} 张)")
                _print(f"[+] 标题: {title}")
                if author:
                    _print(f"[+] 作者: {author}")

                # 创建图集子目录
                folder_name = _sanitize_filename(title)
                image_dir = output_path / folder_name
                image_dir.mkdir(parents=True, exist_ok=True)

                # 使用浏览器 fetch 逐张下载图片（绕过 403）
                total_size = 0
                ok_count = 0
                fail_count = 0

                for i, img_url in enumerate(image_urls, 1):
                    ext = ".webp"
                    if ".jpeg" in img_url or ".jpg" in img_url:
                        ext = ".jpg"
                    elif ".png" in img_url:
                        ext = ".png"

                    filename = f"{i:03d}{ext}"
                    file_path = image_dir / filename

                    if file_path.exists() and file_path.stat().st_size > 0:
                        ok_count += 1
                        continue

                    _print(f"  [{i}/{len(image_urls)}] 下载: {filename}")
                    try:
                        size = _download_image_via_playwright(page, img_url, file_path)
                        total_size += size
                        ok_count += 1
                    except Exception as e:
                        fail_count += 1
                        _print(f"  [!] 第 {i} 张下载失败: {e}")

                return {
                    "type": "image",
                    "title": title,
                    "author": author,
                    "image_count": len(image_urls),
                    "image_dir": str(image_dir),
                    "ok_count": ok_count,
                    "fail_count": fail_count,
                    "total_size": total_size,
                }

            else:
                raise RuntimeError(
                    "无法判断页面内容类型。"
                    "请确认链接是有效的抖音视频或图集链接。"
                )

        finally:
            browser.close()


# ── 向后兼容 ──
def download_douyin_video(url: str, output_dir: str = "") -> dict:
    """下载抖音无水印视频（兼容旧接口，推荐使用 download_douyin）"""
    return download_douyin(url, output_dir)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python downloader.py <抖音链接>")
        print("支持: 视频 / 图文笔记")
        sys.exit(1)

    result = download_douyin(sys.argv[1])

    if result["type"] == "video":
        size_mb = result["file_size"] / (1024 * 1024)
        _print(f"\n[OK] 视频下载完成!")
        _print(f"   文件: {result['file_path']}")
        _print(f"   大小: {size_mb:.2f} MB")
    else:
        size_mb = result["total_size"] / (1024 * 1024)
        _print(f"\n[OK] 图集下载完成!")
        _print(f"   目录: {result['image_dir']}")
        _print(f"   成功: {result['ok_count']}/{result['image_count']} 张")
        if result["fail_count"]:
            _print(f"   失败: {result['fail_count']} 张")
        _print(f"   大小: {size_mb:.2f} MB")

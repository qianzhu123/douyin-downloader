"""Douyin watermark-free video/image downloader - CLI entry"""

import argparse
import re
import sys
from pathlib import Path

from downloader import download_douyin


def _extract_url(raw: str) -> str:
    """
    Extract Douyin URL from raw paste text.

    Accepts:
    - Direct URL: https://v.douyin.com/xxxxx/
    - Share text: "6.99 02/11 hOk:/ ... https://v.douyin.com/xxxxx/ ..."
    - Full URL: https://www.douyin.com/video/7xxx or /note/7xxx
    """
    raw = raw.strip()
    # Try to find a Douyin URL in the text
    patterns = [
        r'(https?://v\.douyin\.com/\S+)',
        r'(https?://www\.douyin\.com/(?:video|note)/\S+)',
    ]
    for pat in patterns:
        m = re.search(pat, raw)
        if m:
            url = m.group(1)
            # Remove trailing punctuation from share text (e.g. trailing colon, Chinese colon)
            url = re.sub(r'[:：。，]+$', '', url)
            return url
    # If no URL pattern found, return as-is (might still work)
    return raw


def _read_urls_from_file(file_path: str) -> list[str]:
    """Read URLs from a file, one per line. Skips empty lines and comments."""
    path = Path(file_path)
    if not path.exists():
        print(f"[ERROR] File not found: {file_path}")
        sys.exit(1)

    urls = []
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue
        urls.append(line)

    if not urls:
        print(f"[ERROR] No valid URLs found in: {file_path}")
        sys.exit(1)

    return urls


def _download_one(url: str, output_dir: str) -> dict:
    """Download a single Douyin URL and return the result."""
    clean_url = _extract_url(url)
    if clean_url != url:
        print(f"[INFO] Extracted URL: {clean_url}")

    try:
        result = download_douyin(clean_url, output_dir)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"\n[X] Download failed: {e}")
        return None

    return result


def _print_result(result: dict):
    """Pretty-print a download result."""
    if not result:
        return

    print()
    if result["type"] == "video":
        size_mb = result["file_size"] / (1024 * 1024)
        print("[OK] Video downloaded!")
        print(f"   Title:  {result['title']}")
        if result["author"]:
            print(f"   Author: {result['author']}")
        print(f"   File:   {result['file_path']}")
        print(f"   Size:   {size_mb:.2f} MB")
    else:
        size_mb = result["total_size"] / (1024 * 1024)
        print("[OK] Image collection downloaded!")
        print(f"   Title:  {result['title']}")
        if result["author"]:
            print(f"   Author: {result['author']}")
        print(f"   Count:  {result['ok_count']}/{result['image_count']} images")
        if result["fail_count"]:
            print(f"   Failed: {result['fail_count']} images")
        print(f"   Dir:    {result['image_dir']}")
        print(f"   Size:   {size_mb:.2f} MB")


def main():
    parser = argparse.ArgumentParser(
        description="Douyin watermark-free downloader",
        epilog=(
            "Examples:\n"
            "  python main.py https://v.douyin.com/xxxxx/\n"
            "  python main.py https://v.douyin.com/aaa/ https://v.douyin.com/bbb/\n"
            "  python main.py -f urls.txt\n"
            "  python main.py -f urls.txt -o ./my_downloads"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="Douyin URL(s) or share text (supports multiple)",
    )
    parser.add_argument(
        "-f", "--file",
        default="",
        help="Read URLs from a text file (one URL per line, # comments supported)",
    )
    parser.add_argument(
        "-o", "--output",
        default="",
        help="Output directory (default: ./downloads/)",
    )

    args = parser.parse_args()

    # Collect all URLs
    all_urls: list[str] = []

    if args.file:
        file_urls = _read_urls_from_file(args.file)
        all_urls.extend(file_urls)
        print(f"[INFO] Loaded {len(file_urls)} URL(s) from: {args.file}")

    if args.urls:
        all_urls.extend(args.urls)

    if not all_urls:
        parser.error("No URLs provided. Pass URLs as arguments or use -f/--file to read from a file.")

    print(f"[INFO] Total: {len(all_urls)} URL(s) to download")
    print(f"[INFO] Output: {args.output or './downloads/'}")
    print()

    # Download each URL
    ok = 0
    fail = 0
    for i, url in enumerate(all_urls, 1):
        print(f"{'=' * 50}")
        print(f"[{i}/{len(all_urls)}] Processing: {url}")
        print(f"{'=' * 50}")
        result = _download_one(url, args.output)
        if result:
            _print_result(result)
            ok += 1
        else:
            fail += 1

    # Summary
    print()
    print(f"{'=' * 50}")
    print(f"Done! Success: {ok}, Failed: {fail}, Total: {len(all_urls)}")

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

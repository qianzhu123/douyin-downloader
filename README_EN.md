# Douyin Watermark-Free Downloader

> English documentation. The default README is Chinese: [中文 README](./README.md)

A Python + Playwright based downloader for the Douyin web version. It supports downloading watermark-free videos, image collections/notes, mixed Slides content, and optionally exporting interaction statistics and comments as JSON.

GitHub: <https://github.com/qianzhu123/douyin-downloader>

## Features

- Download watermark-free videos as MP4
- Download image collections/notes as WebP/JPG/PNG
- Support mixed Slides/notes content, including videos and images
- Automatically extract URLs from short links, full video links, note links, selected-page links, and share text
- Batch download from a text file
- Custom output directory
- Multi-thread batch processing
- Optional interaction statistics JSON export, including likes, comments, collects, and shares
- Optional main comment scraping, disabled by default because it may be slow or affected by anti-bot checks
- Windows users can run the tool by double-clicking `start.bat`

## Requirements

- Python 3.10 or later, Python 3.11+ is recommended
- Windows / macOS / Linux
- Network access to the Douyin web version

## Installation

### 1. Clone this repository

```bash
git clone https://github.com/qianzhu123/douyin-downloader.git
cd douyin-downloader
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install the Playwright Chromium browser

```bash
playwright install chromium
```

On some Linux environments, you may also need:

```bash
playwright install-deps chromium
```

## Quick Start

### Download a single URL

```bash
python main.py https://v.douyin.com/xxxxx/
```

### Extract URL automatically from share text

```bash
python main.py --input "Paste Douyin share text here https://v.douyin.com/xxxxx/"
```

### Specify output directory

```bash
python main.py https://v.douyin.com/xxxxx/ -o ./downloads
```

### Download multiple URLs

```bash
python main.py https://v.douyin.com/aaaa/ https://v.douyin.com/bbbb/
```

### Read URLs from a file

Create `urls.txt`:

```text
https://v.douyin.com/aaaa/
https://www.douyin.com/video/7xxx
https://www.douyin.com/note/7xxx
```

Run:

```bash
python main.py -f urls.txt
```

### Multi-thread batch processing

```bash
python main.py -f urls.txt -w 3
```

> Avoid using too many workers to reduce the risk of anti-bot checks and high system resource usage.

## Download Modes

| Mode | Option | Description |
|---|---|---|
| Media only | `-m 1` | Default mode. Download videos/images only |
| JSON only | `-m 2` | Export interaction statistics JSON only |
| All | `-m 3` | Download media and export interaction statistics JSON |

Example:

```bash
python main.py https://v.douyin.com/xxxxx/ -m 3
```

## Comment Scraping

Comment scraping is disabled by default. To scrape main comments, add `-c`:

```bash
python main.py https://v.douyin.com/xxxxx/ -m 3 -c
```

Notes:

- Comment scraping may be slow
- Comment APIs may be affected by login status, network conditions, or Douyin anti-bot checks
- The current implementation mainly scrapes main comments and does not guarantee all replies

## Windows Double-Click Usage

Windows users can double-click:

```text
start.bat
```

Then follow the prompts:

1. Enter a Douyin URL, share text, or a file path containing URLs
2. Choose download mode
3. Choose whether to scrape comments
4. Set worker count
5. Set output directory

## Supported URL Formats

| Type | Example |
|---|---|
| Short link | `https://v.douyin.com/xxxxx/` |
| Full video link | `https://www.douyin.com/video/7xxx` |
| Note/image link | `https://www.douyin.com/note/7xxx` |
| Selected-page link | `https://www.douyin.com/jingxuan...` |
| User page with modal ID | `https://www.douyin.com/user/...?...modal_id=7xxx` |
| Share text | Paste the full Douyin share text, and the tool will extract URLs automatically |

## Output Structure

The default output directory is `downloads/` under the current working directory.

```text
downloads/
├── video_title.mp4
├── image_or_note_title/
│   ├── 001.webp
│   ├── 002.jpg
│   └── data.json
└── slide_title/
    ├── slide_title_S01.mp4
    ├── S02.jpg
    └── slide_title.json
```

File names are automatically sanitized based on the work title.

## Command-Line Options

```text
usage: main.py [-h] [--input RAW_INPUT] [-f FILE] [-m {1,2,3}] [-o OUTPUT] [-w WORKERS] [-c] [urls ...]

positional arguments:
  urls                  Douyin URL(s) or share text

options:
  -h, --help            Show help message and exit
  --input RAW_INPUT     Auto-detect URL, share text, or file path
  -f, --file FILE       Read URLs from a text file, one URL per line
  -m, --mode {1,2,3}    1=media only, 2=JSON only, 3=all
  -o, --output OUTPUT   Output directory, default ./downloads/
  -w, --workers WORKERS Number of parallel workers, default 1
  -c, --comments        Also scrape comments, disabled by default
```

## FAQ

### 1. Browser not found after installation?

Run:

```bash
playwright install chromium
```

### 2. Download failed or page could not be recognized?

Possible reasons:

- The link has expired
- The current network cannot access Douyin web pages
- Douyin page structure has changed
- Anti-bot checks were triggered; try again later

### 3. Why are comments incomplete?

Comment APIs may be affected by anti-bot checks, login status, network conditions, and pagination. Comment scraping is disabled by default to keep media downloading more stable.

## Privacy and Local Files

This project does not require local machine paths, account passwords, or personal local information. Downloaded content is stored under `downloads/` by default, and that directory is included in `.gitignore`, so it will not be committed with the repository.

## Disclaimer

This project is for learning and personal backup only. Please comply with applicable laws, platform rules, and original creators' copyrights. Do not use this tool for copyright infringement or any activity that violates platform rules.

## License

MIT

## Contact

If you encounter any issues, feel free to contact me:

- WeChat: `e3075588361`

---

For Chinese documentation, see: [README.md](./README.md)

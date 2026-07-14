# 抖音无水印下载器

> 默认中文文档。需要英文说明请切换到：[English README](./README_EN.md)

一个基于 Python + Playwright 的抖音网页端下载工具，支持下载抖音无水印视频、图集/笔记图片、Slides 混合内容，并可选择导出互动数据与评论 JSON。

GitHub：<https://github.com/qianzhu123/douyin-downloader>

## 功能特性

- 支持下载无水印视频（MP4）
- 支持下载图集/笔记图片（WebP/JPG/PNG）
- 支持 Slides/笔记混合内容（视频 + 图片）
- 自动识别短链接、完整视频链接、图文链接、精选页链接和分享文本
- 支持从文件批量读取链接
- 支持自定义输出目录
- 支持多线程批量处理
- 可选导出互动数据 JSON（点赞、评论数、收藏、转发等）
- 可选抓取主评论（默认关闭，因评论接口可能较慢或受风控影响）
- Windows 可双击 `start.bat` 使用

## 环境要求

- Python 3.10 或更高版本（建议 3.11+）
- Windows / macOS / Linux
- 网络可访问抖音网页端

## 安装依赖

### 1. 克隆项目

```bash
git clone https://github.com/qianzhu123/douyin-downloader.git
cd douyin-downloader
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 安装 Playwright 浏览器内核

```bash
playwright install chromium
```

如果你使用的是某些 Linux 环境，可能还需要：

```bash
playwright install-deps chromium
```

## 快速使用

### 下载单个链接

```bash
python main.py https://v.douyin.com/xxxxx/
```

### 从分享文本中自动提取链接

```bash
python main.py --input "这里粘贴抖音分享文本 https://v.douyin.com/xxxxx/"
```

### 指定输出目录

```bash
python main.py https://v.douyin.com/xxxxx/ -o ./downloads
```

### 批量下载多个链接

```bash
python main.py https://v.douyin.com/aaaa/ https://v.douyin.com/bbbb/
```

### 从文件读取链接

创建 `urls.txt`：

```text
https://v.douyin.com/aaaa/
https://www.douyin.com/video/7xxx
https://www.douyin.com/note/7xxx
```

运行：

```bash
python main.py -f urls.txt
```

### 多线程批量处理

```bash
python main.py -f urls.txt -w 3
```

> 建议线程数不要过高，避免触发网站风控或占用过多系统资源。

## 下载模式

程序支持三种模式：

| 模式 | 参数 | 说明 |
|---|---|---|
| 仅下载媒体 | `-m 1` | 默认模式，仅下载视频/图片 |
| 仅导出数据 | `-m 2` | 只保存互动数据 JSON，不下载媒体 |
| 全部保存 | `-m 3` | 下载媒体并保存互动数据 JSON |

示例：

```bash
python main.py https://v.douyin.com/xxxxx/ -m 3
```

## 评论抓取

评论抓取默认关闭。如需抓取主评论，请添加 `-c`：

```bash
python main.py https://v.douyin.com/xxxxx/ -m 3 -c
```

注意：

- 评论抓取可能较慢
- 评论接口可能受登录状态、网络环境或抖音风控影响
- 当前主要抓取主评论，不保证抓取全部回复

## Windows 双击使用

Windows 用户可直接双击：

```text
start.bat
```

按提示输入：

1. 抖音链接、分享文本或链接文件路径
2. 下载模式
3. 是否抓取评论
4. 并行线程数
5. 输出目录

## 支持的链接格式

| 类型 | 示例 |
|---|---|
| 短链接 | `https://v.douyin.com/xxxxx/` |
| 视频链接 | `https://www.douyin.com/video/7xxx` |
| 图文/笔记链接 | `https://www.douyin.com/note/7xxx` |
| 精选页链接 | `https://www.douyin.com/jingxuan...` |
| 用户页带作品弹窗 | `https://www.douyin.com/user/...?...modal_id=7xxx` |
| 分享文本 | `复制整段抖音分享文本，程序会自动提取链接` |

## 输出结构

默认输出目录为当前目录下的 `downloads/`。

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

实际文件名会根据作品标题自动清理非法字符。

## 命令行参数

```text
usage: main.py [-h] [--input RAW_INPUT] [-f FILE] [-m {1,2,3}] [-o OUTPUT] [-w WORKERS] [-c] [urls ...]

positional arguments:
  urls                  抖音链接或分享文本

options:
  -h, --help            显示帮助信息
  --input RAW_INPUT     自动识别链接、分享文本或文件路径
  -f, --file FILE       从文本文件读取链接（一行一个）
  -m, --mode {1,2,3}    1=仅下载媒体，2=仅数据 JSON，3=全部
  -o, --output OUTPUT   输出目录，默认 ./downloads/
  -w, --workers WORKERS 并行线程数，默认 1
  -c, --comments        同时抓取评论（默认关闭）
```

## 常见问题

### 1. 安装后运行提示找不到浏览器？

请执行：

```bash
playwright install chromium
```

### 2. 下载失败或无法识别页面？

可能原因：

- 链接已失效
- 当前网络无法访问抖音网页端
- 抖音页面结构变更
- 触发风控，需要稍后重试

### 3. 为什么评论抓取不完整？

评论接口可能受风控、登录状态、网络和分页策略影响。程序默认关闭评论抓取，以保证媒体下载更稳定。

## 隐私与本地文件说明

项目不会要求填写本机路径、账号密码或本地个人信息。下载内容默认保存在 `downloads/`，该目录已加入 `.gitignore`，不会随项目提交。

## 免责声明

本项目仅供学习与个人备份使用。请遵守相关法律法规、平台规则以及原作者版权要求。请勿将本工具用于侵犯他人权益或违反平台规则的用途。

## License

MIT

## 联系方式

如使用过程中遇到问题，可联系我：

- 微信：`e3075588361`

---

需要英文文档请查看：[README_EN.md](./README_EN.md)

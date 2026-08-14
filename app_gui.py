"""抖音无水印下载器 - PyQt5 桌面可视化界面。

用法:
    python app_gui.py

特性:
- 粘贴抖音链接 → 解析预览 → 显示媒体网格(缩略图/视频帧 + 类型角标)
- 勾选要下载的媒体(可全选/反选/单选)
- 选择输出目录、是否同时抓评论
- 后台线程下载，进度条 + 日志实时显示
- 复用 douyin_profile 登录态(先运行 init_login.py)
"""
import os
import re
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import httpx
from PyQt5 import QtCore, QtGui, QtWidgets

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from src.downloader import extract_preview, download_douyin, _download_file, _sanitize_filename  # noqa: E402

APP_NAME = "抖音下载器"
QS = QtCore.QSize

# ── 深色主题（统一字号/灰阶/层次，避免大小不一与暗淡） ─────────
# 灰阶：正文 #f0f1f3 · 次要 #b8bdc4 · 提示 #8a909a · 背景 #25272b · 卡片/输入 #2d3036 · 边框 #3c4048
QSS = """
* { font-family: "Microsoft YaHei UI","Microsoft YaHei","Segoe UI"; }
QMainWindow, QWidget#central { background: #25272b; color: #f0f1f3; }
QLabel { color: #f0f1f3; background: transparent; }
QWidget#card, QGroupBox, QListWidget, QPlainTextEdit, QLineEdit, QTextEdit {
  background: #2d3036; color: #f0f1f3; border: 1px solid #3c4048;
  border-radius: 8px; padding: 6px;
}
QLineEdit, QPlainTextEdit, QTextEdit { selection-background-color: #2f8cff; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus { border-color: #2f8cff; }
QLineEdit { padding: 10px 14px; }

QPushButton {
  background: #2f8cff; color: #ffffff; border: none; border-radius: 8px;
  padding: 12px 26px; font-weight: 600; min-height: 28px;
}
QPushButton:hover { background: #4a9bff; }
QPushButton:pressed { background: #2570d8; }
QPushButton:disabled { background: #3c4048; color: #6a6f78; }
QPushButton[role="secondary"] { background: #3c4048; color: #f0f1f3; }
QPushButton[role="secondary"]:hover { background: #4a4f57; }
QPushButton[role="danger"] { background: #d2473a; color: #ffffff; }
QPushButton[role="danger"]:hover { background: #e25a4d; }

QCheckBox { color: #f0f1f3; spacing: 8px; background: transparent; }

QProgressBar {
  background: #2d3036; border: 1px solid #3c4048; border-radius: 8px;
  text-align: center; color: #f0f1f3; height: 26px; min-height: 26px;
}
QProgressBar::chunk { background: #2f8cff; border-radius: 7px; }

QListWidget { border-radius: 8px; outline: 0; }
QListWidget::item { padding: 10px; border-radius: 6px; }
QListWidget::item:selected { background: #2f8cff; color: #ffffff; }

QStatusBar { background: #25272b; color: #f0f1f3; font-weight: 600; border-top: 1px solid #3c4048; }
QStatusBar QLabel { color: #f0f1f3; padding: 2px 6px; }

QMessageBox { background: #2d3036; }
QMessageBox QLabel, QMessageBox QTextEdit { color: #f0f1f3; }
QMessageBox QPushButton {
  background: #2f8cff; color: #ffffff; border: none; border-radius: 8px;
  padding: 10px 28px; font-weight: 600; min-width: 110px;
}
QMessageBox QPushButton:hover { background: #4a9bff; }
QMessageBox QPushButton[role="secondary"] { background: #3c4048; color: #f0f1f3; }
QDBusArgument { } /* noop */

QDialog { background: #25272b; color: #f0f1f3; }
QToolTip { color: #f0f1f3; background: #2d3036; border: 1px solid #2f8cff; padding: 4px 8px; }

QScrollBar:vertical { background: transparent; width: 12px; border: none; margin: 2px; }
QScrollBar::handle:vertical { background: #4a4f57; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #5a5f68; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; height: 0; width: 0; }
QScrollBar:horizontal { background: transparent; height: 12px; border: none; margin: 2px; }
QScrollBar::handle:horizontal { background: #4a4f57; border-radius: 5px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: #5a5f68; }

QSplitter::handle { background: #3c4048; }
QSplitter::handle:hover { background: #2f8cff; }

QGroupBox { margin-top: 14px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #b8bdc4; }
"""

TYP_BADGE = {"video": "📹 视频", "image": "🖼 图片", "unknown": "❓"}


def _fmt_stats(s: dict) -> str:
    if not s:
        return ""
    def n(v):
        v = int(v or 0)
        return f"{v//10000}万" if v >= 10000 else str(v)
    parts = []
    if s.get("digg_count"): parts.append(f"点赞 {n(s['digg_count'])}")
    if s.get("comment_count"): parts.append(f"评论 {n(s['comment_count'])}")
    if s.get("collect_count"): parts.append(f"收藏 {n(s['collect_count'])}")
    if s.get("share_count"): parts.append(f"转发 {n(s['share_count'])}")
    return " · ".join(parts) if parts else "无互动数据"


# ── 后台解析预览线程 ────────────────────────────────────────
class PreviewWorker(QtCore.QObject):
    done = QtCore.pyqtSignal(dict)
    log = QtCore.pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    @QtCore.pyqtSlot()
    def run(self):
        self.log.emit(f"[*] 解析中: {self.url}")
        try:
            r = extract_preview(self.url)
            self.done.emit(r)
        except Exception as e:
            self.done.emit({"url": self.url, "type": "unknown", "items": [], "error": str(e)})


# ── 缩略图异步加载 ──────────────────────────────────────────
class ThumbLoader(QtCore.QThread):
    loaded = QtCore.pyqtSignal(int, QtGui.QPixmap)

    def __init__(self, items):
        super().__init__()
        self.items = items
        self._stop = False

    def run(self):
        with ThreadPoolExecutor(max_workers=4) as ex:
            for i, it in enumerate(self.items):
                if self._stop:
                    return
                url = it.get("cover_url") or ""
                if not url:
                    continue
                ex.submit(self._fetch, i, url)

    def _fetch(self, i, url):
        if self._stop:
            return
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.douyin.com/"})
            pix = QtGui.QPixmap()
            pix.loadFromData(r.content)
            if not pix.isNull():
                self.loaded.emit(i, pix)
        except Exception:
            pass

    def stop(self):
        self._stop = True


# ── 下载线程 ───────────────────────────────────────────────
class LoginWorker(QtCore.QObject):
    log = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(bool, str)  # ok, message

    def __init__(self, prof_str: str):
        super().__init__()
        self.prof_str = prof_str

    @QtCore.pyqtSlot()
    def run(self):
        from pathlib import Path as _P
        from src.init_login import login_interactive, profile_path, check_login
        prof = _P(self.prof_str)
        self.log.emit(f"[*] 启动登录浏览器，profile → {prof}")
        self.log.emit("[*] 请在弹出窗口扫码登录抖音(可慢，收到验证码再填)")
        self.log.emit("[*] 登录成功会自动检测并完成；浏览器可随时手动关闭")
        ok = login_interactive(
            prof, headless=False, timeout_sec=1800,
            block_console=False,
            on_progress=lambda s: self.log.emit(s),
        )
        ok2, msg2 = check_login(prof)
        self.finished.emit(ok2, msg2)


class DownloadWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)   # done, total
    log = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(int, int)   # ok, fail

    def __init__(self, url, out_dir, items_to_download, fetch_comments):
        super().__init__()
        self.url = url
        self.out_dir = out_dir
        self.items = items_to_download
        self.fetch_comments = fetch_comments
        self._cancel = False

    @QtCore.pyqtSlot()
    def run(self):
        ok = fail = 0
        total = len(self.items)
        if total == 0:
            self.log.emit("[x] 没有勾选任何媒体")
            self.finished.emit(0, 0)
            return
        out = Path(self.out_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 若全选 → 整作品下载(含数据JSON/评论由 download_douyin 统一编排)
        if total > 0 and self._all_selected():
            self.log.emit(f"[*] 全选，整作品下载到: {out}")
            try:
                r = download_douyin(self.url, output_dir=str(out),
                                    mode=1, fetch_comments=self.fetch_comments)
                self.log.emit(f"[+] 完成: {r.get('title','')[:40]} → {r.get('file_path') or r.get('folder','')}")
                ok = 1
            except Exception as e:
                self.log.emit(f"[x] 下载失败: {e}")
                fail = 1
            self.progress.emit(ok if ok else 1, 1)
            self.finished.emit(ok, fail)
            return

        # 部分勾选 → 逐页用 _download_file 直接下
        base_title = self._title_for_files()
        folder = out
        if self.items[0].get("__kind") == "slide":
            folder = out / _sanitize_filename(base_title)
            folder.mkdir(parents=True, exist_ok=True)
        for n, it in enumerate(self.items, 1):
            if self._cancel:
                self.log.emit("[!] 已取消")
                break
            mt = it.get("media_type", "image")
            idx = it.get("index", n - 1) + 1
            try:
                if mt == "video":
                    vu = it.get("video_url", "")
                    if not vu:
                        self.log.emit(f"  [{n}/{total}] 第{idx}页无视频直链，跳过")
                        fail += 1
                        self.progress.emit(ok + fail, total)
                        continue
                    fn = folder / f"{_sanitize_filename(base_title)}_S{idx:02d}.mp4"
                    self.log.emit(f"  [{n}/{total}] 下载视频 第{idx}页 → {fn.name}")
                    _download_file(vu, fn)
                    ok += 1
                else:
                    iu = it.get("cover_url") or (it.get("image_urls") or [""])[0]
                    if not iu:
                        self.log.emit(f"  [{n}/{total}] 第{idx}页无图片地址，跳过")
                        fail += 1
                        self.progress.emit(ok + fail, total)
                        continue
                    ext = ".jpg" if (".jpeg" in iu or ".jpg" in iu) else (".png" if ".png" in iu else ".webp")
                    fn = folder / f"{_sanitize_filename(base_title)}_{idx:02d}{ext}"
                    self.log.emit(f"  [{n}/{total}] 下载图片 第{idx}页 → {fn.name}")
                    _download_file(iu, fn)
                    ok += 1
                self.progress.emit(ok + fail, total)
            except Exception as e:
                fail += 1
                self.log.emit(f"  [!] 第{idx}页失败: {e}")
                self.progress.emit(ok + fail, total)
        self.finished.emit(ok, fail)

    def _all_selected(self):
        return False  # 在 MainWindow 持有完整列表时另行判断；见下方 MainWindow.download

    def _title_for_files(self):
        return self.__dict__.get("_title", "douyin") or "douyin"

    def cancel(self):
        self._cancel = True


# ── 媒体卡片项 ─────────────────────────────────────────────
class MediaItemWidget(QtWidgets.QWidget):
    def __init__(self, index, media_type, cover_url, duration_ms, on_toggle_media):
        super().__init__()
        self.index = index
        self.media_type = media_type
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        self.check = QtWidgets.QCheckBox(f"#{index + 1}")
        self.check.setChecked(True)
        self.check.stateChanged.connect(lambda st: on_toggle_media(index, st == QtCore.Qt.Checked))
        # 角标
        badge = QtWidgets.QLabel(TYP_BADGE.get(media_type, ""))
        badge.setStyleSheet("color:#ffe08a;font-weight:700;background:#000000b0;"
                            "padding:1px 8px;border-radius:8px;")
        badge.setFixedSize(72, 20)
        # 缩略图占位
        self.thumb = QtWidgets.QLabel()
        self.thumb.setFixedSize(120, 160)
        self.thumb.setAlignment(QtCore.Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#2d3036;border-radius:8px;color:#6a6f78;border:1px solid #3c4048;")
        self.thumb.setText("加载中…")
        self.duration_lbl = QtWidgets.QLabel("")
        if duration_ms:
            secs = duration_ms // 1000
            self.duration_lbl.setText(f"{secs//60:02d}:{secs%60:02d}")
        self.duration_lbl.setStyleSheet("color:#b8bdc4;background:#000000b0;padding:1px 6px;border-radius:4px;")
        # 叠加角标到缩略图
        overlay = QtWidgets.QHBoxLayout()
        overlay.setContentsMargins(4, 4, 4, 4)
        holder = QtWidgets.QWidget()
        holder.setFixedSize(120, 160)
        ov = QtWidgets.QVBoxLayout(holder)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.addWidget(badge, 0, QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        ov.addStretch()
        ov.addWidget(self.duration_lbl, 0, QtCore.Qt.AlignRight)
        stack = QtWidgets.QStackedLayout()
        stack.setStackingMode(QtWidgets.QStackedLayout.StackingMode.StackAll)
        stack.addWidget(self.thumb)
        stack.addWidget(holder)
        wrap = QtWidgets.QWidget()
        wrap.setLayout(stack)
        wrap.setFixedSize(120, 160)
        layout.addWidget(self.check, 0, QtCore.Qt.AlignLeft)
        layout.addWidget(wrap, 0, QtCore.Qt.AlignHCenter)

    def set_thumb(self, pix: QtGui.QPixmap):
        scaled = pix.scaled(120, 160, QtCore.Qt.KeepAspectRatioByExpanding,
                            QtCore.Qt.SmoothTransformation)
        self.thumb.setPixmap(scaled)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(980, 760)
        self.preview: dict | None = None
        self.items: list[dict] = []  # 当前预览的全部媒体(含 __kind 标记)
        self.thumb_loader: ThumbLoader | None = None
        self.preview_thread: QtCore.QThread | None = None
        self.preview_worker: PreviewWorker | None = None
        self.dl_thread: QtCore.QThread | None = None
        self.dl_worker: DownloadWorker | None = None
        self._build_ui()
        self._default_out_dir()

    def _default_out_dir(self):
        from src.paths import default_download_dir
        d = str(default_download_dir())
        self.out_edit.setText(d)

    def _build_ui(self):
        central = QtWidgets.QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ── 顶部：链接输入 + 解析预览 ──
        top = QtWidgets.QHBoxLayout()
        self.url_edit = QtWidgets.QLineEdit()
        self.url_edit.setPlaceholderText("粘贴抖音链接 / user/self?modal_id=... 喜欢列表 / 分享文案…")
        self.url_edit.returnPressed.connect(self.do_preview)
        top.addWidget(self.url_edit, 1)
        self.btn_preview = QtWidgets.QPushButton("解析预览")
        self.btn_preview.clicked.connect(self.do_preview)
        top.addWidget(self.btn_preview)
        root.addLayout(top)

        # ── 输出目录 ──
        out_row = QtWidgets.QHBoxLayout()
        out_row.addWidget(QtWidgets.QLabel("输出目录:"))
        self.out_edit = QtWidgets.QLineEdit()
        out_row.addWidget(self.out_edit, 1)
        btn_pick = QtWidgets.QPushButton("更改…")
        btn_pick.setProperty("role", "secondary")
        btn_pick.clicked.connect(self.pick_dir)
        out_row.addWidget(btn_pick)
        root.addLayout(out_row)

        # ── 信息条 ──
        self.title_lbl = QtWidgets.QLabel("尚未解析")
        self.title_lbl.setStyleSheet("font-weight:600;padding:4px 0;")
        root.addWidget(self.title_lbl)
        self.stats_lbl = QtWidgets.QLabel("")
        self.stats_lbl.setStyleSheet("color:#b8bdc4;")
        root.addWidget(self.stats_lbl)

        # ── 媒体网格 + 选择控件 ──
        sel_row = QtWidgets.QHBoxLayout()
        self.check_comments = QtWidgets.QCheckBox("同时抓评论")
        self.check_all = QtWidgets.QCheckBox("全选")
        self.check_all.setChecked(True)
        self.check_all.stateChanged.connect(self.toggle_all)
        sel_row.addWidget(self.check_all)
        btn_none = QtWidgets.QPushButton("全不选")
        btn_none.setProperty("role", "secondary")
        btn_none.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(btn_none)
        sel_row.addStretch()
        sel_row.addWidget(self.check_comments)
        root.addLayout(sel_row)

        self.media_list = QtWidgets.QListWidget()
        self.media_list.setFlow(QtWidgets.QListView.LeftToRight)
        self.media_list.setWrapping(True)
        self.media_list.setResizeMode(QtWidgets.QListView.Adjust)
        self.media_list.setSpacing(8)
        self.media_list.setViewMode(QtWidgets.QListView.IconMode)
        self.media_list.setIconSize(QS(120, 160))
        root.addWidget(self.media_list, 1)

        # ── 下载按钮 + 进度 ──
        bot = QtWidgets.QHBoxLayout()
        self.btn_download = QtWidgets.QPushButton("下载已选")
        self.btn_download.clicked.connect(self.do_download)
        self.btn_download.setEnabled(False)
        self.btn_cancel = QtWidgets.QPushButton("取消")
        self.btn_cancel.setProperty("role", "secondary")
        self.btn_cancel.clicked.connect(self.cancel_download)
        self.btn_cancel.setEnabled(False)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setValue(0)
        bot.addWidget(self.btn_download)
        bot.addWidget(self.btn_cancel)
        bot.addWidget(self.progress, 1)
        root.addLayout(bot)

        # ── 日志 ──
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(160)
        root.addWidget(self.log_view)

        self.status = self.statusBar()
        self.btn_login = QtWidgets.QPushButton("登录")
        self.btn_login.setProperty("role", "secondary")
        self.btn_login.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_login.clicked.connect(self.start_login)
        self.status.addPermanentWidget(self.btn_login)
        self._lw_alive = False
        self.status.showMessage(f"{APP_NAME} · 就绪")

    # ── 登录(子线程，避免阻塞 UI) ──
    def start_login(self):
        if self._lw_alive:
            self.log("[*] 登录已在进行中，请先在弹出窗口扫码")
            return
        from src.init_login import profile_path
        prof = profile_path()
        try:
            from src.init_login import check_login
            ok, _ = check_login(prof)
            if ok:
                self.log("[+] 当前已登录。如需换号继续点登录即可。")
        except Exception:
            pass
        self.log(f"[*] 开始登录，profile → {prof}")
        self.status.showMessage("登录中…请扫码")
        self.btn_login.setEnabled(False)
        self._lw_alive = True
        self._login_thread = QtCore.QThread()
        self._login_worker = LoginWorker(str(prof))
        self._login_worker.moveToThread(self._login_thread)
        self._login_worker.log.connect(self.log)
        self._login_thread.started.connect(self._login_worker.run)
        self._login_worker.finished.connect(self._on_login_done)
        self._login_worker.finished.connect(self._login_thread.quit)
        self._login_thread.start()

    def _on_login_done(self, ok, msg):
        self._lw_alive = False
        self.btn_login.setEnabled(True)
        if ok:
            self.log(f"[+] {msg}")
            self.status.showMessage(f"已登录 · {msg}")
            QtWidgets.QMessageBox.information(self, "登录成功", f"{msg}")
        else:
            self.log(f"[x] 登录未完成: {msg}")
            self.status.showMessage("登录未完成 —— 可重新点登录")
            QtWidgets.QMessageBox.warning(self, "登录未完成",
                "未检测到登录态。请确认已在弹出窗口完成扫码，再点【登录】重试。\n"
                f"详情：{msg}")

    # ── 解析预览 ──
    def do_preview(self):
        url = self.url_edit.text().strip()
        if not url:
            self.log("请粘贴抖音链接")
            return
        self.btn_preview.setEnabled(False)
        self.btn_download.setEnabled(False)
        self.title_lbl.setText("解析中…")
        self.stats_lbl.setText("")
        self.media_list.clear()
        self.items = []

        self.preview_thread = QtCore.QThread()
        self.preview_worker = PreviewWorker(url)
        self.preview_worker.moveToThread(self.preview_thread)
        self.preview_thread.started.connect(self.preview_worker.run)
        self.preview_worker.log.connect(self.log)
        self.preview_worker.done.connect(self.on_preview_done)
        self.preview_worker.done.connect(self.preview_thread.quit)
        self.preview_thread.start()

    def on_preview_done(self, r: dict):
        self.btn_preview.setEnabled(True)
        self.preview = r
        if r.get("error"):
            self.title_lbl.setText(f"解析失败: {r['error']}")
            self.log(f"[x] 解析失败: {r['error']}")
            return
        kind = r.get("type", "unknown")
        title = r.get("title", "") or "(无标题)"
        self.title_lbl.setText(f"{TYP_BADGE.get(kind, '')}  {title}")
        self.stats_lbl.setText(_fmt_stats(r.get("stats", {})))
        raw = r.get("items", [])
        self.items = []
        for it in raw:
            d = dict(it)
            d["__kind"] = kind
            self.items.append(d)
        self.check_all.setChecked(True)
        self._populate()
        self.btn_download.setEnabled(bool(self.items))
        self.log(f"[+] 解析完成: {kind}，{len(self.items)} 个媒体")

    def _populate(self):
        self.media_list.clear()
        if self.thumb_loader:
            self.thumb_loader.stop()
        for i, it in enumerate(self.items):
            w = MediaItemWidget(i, it.get("media_type", "image"),
                                it.get("cover_url", ""), it.get("duration_ms", 0),
                                self.on_toggle_one)
            item = QtWidgets.QListWidgetItem(self.media_list)
            item.setSizeHint(QS(132, 220))
            self.media_list.setItemWidget(item, w)
        # 异步加载缩略图
        self.thumb_loader = ThumbLoader(self.items)
        self.thumb_loader.loaded.connect(self._set_thumb)
        self.thumb_loader.start()

    def _set_thumb(self, i, pix):
        if i >= self.media_list.count():
            return
        wi = self.media_list.item(i)
        if not wi:
            return
        w = self.media_list.itemWidget(wi)
        if isinstance(w, MediaItemWidget):
            w.set_thumb(pix)

    def on_toggle_one(self, index, checked):
        if 0 <= index < len(self.items):
            self.items[index]["__selected"] = checked

    def toggle_all(self, state):
        checked = state == QtCore.Qt.Checked
        self._set_all(checked)

    def _set_all(self, checked):
        for it in self.items:
            it["__selected"] = checked
        for i in range(self.media_list.count()):
            wi = self.media_list.item(i)
            w = self.media_list.itemWidget(wi)
            if isinstance(w, MediaItemWidget):
                w.check.blockSignals(True)
                w.check.setChecked(checked)
                w.check.blockSignals(False)
        self.check_all.blockSignals(True)
        self.check_all.setChecked(checked)
        self.check_all.blockSignals(False)

    def pick_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "选择输出目录", self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    # ── 下载 ──
    def do_download(self):
        if not self.items:
            return
        out = self.out_edit.text().strip()
        if not out:
            self.log("请设置输出目录")
            return
        if not self.preview:
            return
        total = len(self.items)
        selected_mask = [it.get("__selected", True) for it in self.items]
        all_sel = all(m for m in selected_mask)
        # 全选 → 整作品下载；否则逐页下
        if all_sel:
            items_to_run = []  # 空表示走整作品路径占位
            # 复用走 worker 的全选分支
            to_download = [{"__all": True, "kind": self.preview.get("type"), "title": self.preview.get("title", "douyin")}]
        else:
            selected = [it for it in self.items if it.get("__selected", True)]
            if not selected:
                self.log("未勾选任何媒体")
                return
            to_download = selected
        fetch_c = self.check_comments.isChecked()

        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self._dl_all_flag = all_sel

        self.dl_thread = QtCore.QThread()
        worker = DownloadWorker(self.url_edit.text().strip(), out, to_download, fetch_c)
        worker._title = self.preview.get("title", "douyin")
        # 让 _all_selected 在全选时返回 True
        worker._all = all_sel
        worker._all_selected = lambda: getattr(worker, "_all", False)
        worker.moveToThread(self.dl_thread)
        self.dl_thread.started.connect(worker.run)
        worker.progress.connect(self.on_dl_progress)
        worker.log.connect(self.log)
        worker.finished.connect(self.on_dl_finished)
        worker.finished.connect(self.dl_thread.quit)
        self.dl_worker = worker
        self.dl_thread.start()

    def on_dl_progress(self, done, total):
        if total <= 0:
            return
        self.progress.setValue(int(done / total * 100))
        self.status.showMessage(f"下载进度 {done}/{total}")

    def on_dl_finished(self, ok, fail):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.log(f"[完成] 成功 {ok}，失败 {fail}")
        self.status.showMessage(f"完成: 成功 {ok} / 失败 {fail}")

    def cancel_download(self):
        if self.dl_worker:
            self.dl_worker.cancel()
            self.log("[*] 取消中…")

    def log(self, msg: str):
        self.log_view.appendPlainText(msg)


def _ensure_chromium():
    """首启自检 chromium 浏览器内核是否已安装；缺失则用 playwright 驱动自动安装。

    采用"探测可执行是否就绪"而非"真起一个浏览器"的方式：
    真起浏览器在打包/无显示环境/被安全软件拦时极易抛异常被误判为未就绪，
    且白白起停一次拖慢首启。downloader 实际用的是 launch_persistent_context，
    与探测方式解耦，避免假阴性误报。
    """
    if _chromium_installed():
        return True
    print("[*] chromium 未就绪，自动安装中(约 150MB，需联网)...")
    try:
        from playwright._impl._driver import compute_driver_executable
        import subprocess
        exe = compute_driver_executable()
        subprocess.run([exe, "install", "chromium"], check=False)
        return _chromium_installed()
    except Exception as e:
        print(f"[x] chromium 自动安装失败: {e}")
        print("    请手动运行: playwright install chromium")
        return False


def _chromium_installed() -> bool:
    """纯文件探测 chromium 内核是否就绪。不启动任何 playwright 进程，
    避免首启白白起停一次 node 驱动、拖慢启动。

    优先用 _point_to_system_chromium 设好的 PLAYWRIGHT_BROWSERS_PATH，
    回退系统默认 %LocalAppData%/ms-playwright。只要任一 chromium-*/chrome-win64/chrome.exe
    存在即算就绪。
    """
    import os, glob
    from src.init_login import _point_to_system_chromium
    _point_to_system_chromium()
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    roots = []
    if base:
        roots.append(Path(base))
    for var in ("LocalAppData", "AppData"):
        b = os.environ.get(var)
        if b:
            roots.append(Path(b) / "ms-playwright")
    for r in roots:
        if not r.exists():
            continue
        for g in glob.glob(str(r / "chromium-*")):
            if (Path(g) / "chrome-win64" / "chrome.exe").exists():
                return True
    return False


def _check_login_hint():
    """profile 登录态自检并提示。"""
    try:
        from src.init_login import check_login, profile_path
        prof = profile_path()
        ok, msg = check_login(prof)
        return ok, msg, prof
    except Exception as e:
        return False, f"自检异常: {e}", None


def main():
    # 必须最早：复用本机 playwright + 让它去系统 chromium 缓存找内核 + 重建 stdio
    try:
        from src.init_login import (_point_to_system_chromium,
                                _ensure_stdio_for_frozen,
                                _use_system_playwright)
        _use_system_playwright()
        _point_to_system_chromium()
        _ensure_stdio_for_frozen()
    except Exception:
        pass
    app = QtWidgets.QApplication(sys.argv)
    # 全局放大字体，解决界面文字偏小看不清
    _f = app.font()
    _f.setPointSize(max(_f.pointSize() or 9, 11))
    _f.setFamily("Microsoft YaHei UI, Microsoft YaHei, Segoe UI")
    app.setFont(_f)
    app.setStyleSheet(QSS)
    ico = HERE / "assets" / "app_icon.ico"
    if ico.exists():
        app.setWindowIcon(QtGui.QIcon(str(ico)))
    # chromium 自检(缺则自动安装)
    if not _ensure_chromium():
        QtWidgets.QMessageBox.warning(None, APP_NAME,
            "chromium 浏览器未能就绪，请在终端运行:\nplaywright install chromium\n再启动本程序。")
    w = MainWindow()
    w.show()
    # 登录态提示
    ok, msg, prof = _check_login_hint()
    if not ok:
        box = QtWidgets.QMessageBox(w)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("登录态未就绪")
        box.setText("检测到登录态缺失：")
        box.setInformativeText(
            f"{msg}\n\n未登录时，喜欢列表/私密链接可能无法下载。\n"
            f"点【立即登录】会弹出浏览器，扫码登录抖音即可。")
        btn_login = box.addButton("立即登录", QtWidgets.QMessageBox.AcceptRole)
        box.addButton("以后再说", QtWidgets.QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is btn_login:
            w.start_login()
        else:
            w.status.showMessage("未登录 —— 状态栏右侧登录后再下载")
    else:
        w.status.showMessage(f"已就绪 · {msg}")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

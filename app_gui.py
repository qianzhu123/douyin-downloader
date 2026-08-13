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
from downloader import extract_preview, download_douyin, _download_file, _sanitize_filename  # noqa: E402

APP_NAME = "抖音下载器"
QS = QtCore.QSize

# ── 深色主题 ────────────────────────────────────────────────
QSS = """
QMainWindow, QWidget#central { background: #1e1f22; }
QLabel { color: #e6e6e6; }
QLineEdit, QPlainTextEdit, QTextEdit {
  background: #2a2b2f; color: #e6e6e6; border: 1px solid #3a3b40;
  border-radius: 6px; padding: 6px;
}
QLineEdit:focus, QPlainTextEdit:focus { border-color: #2f8cff; }
QPushButton {
  background: #2f8cff; color: #fff; border: none; border-radius: 6px;
  padding: 8px 18px; font-weight: 600;
}
QPushButton:hover { background: #4a9bff; }
QPushButton:pressed { background: #2570d8; }
QPushButton:disabled { background: #44454a; color: #888; }
QPushButton[role="secondary"] { background: #3a3b40; color: #e6e6e6; }
QPushButton[role="secondary"]:hover { background: #4a4b50; }
QCheckBox { color: #e6e6e6; spacing: 6px; }
QProgressBar {
  background: #2a2b2f; border: 1px solid #3a3b40; border-radius: 6px;
  text-align: center; color: #e6e6e6; height: 22px;
}
QProgressBar::chunk { background: #2f8cff; border-radius: 5px; }
QListWidget {
  background: #232428; color: #e6e6e6; border: 1px solid #3a3b40;
  border-radius: 6px;
}
QListWidget::item { padding: 8px; }
QStatusBar { background: #1a1b1e; color: #aaa; }
QScrollBar:vertical { background: #2a2b2f; width: 10px; border: none; }
QScrollBar::handle:vertical { background: #4a4b50; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #3a3b40; }
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
        badge.setStyleSheet("color:#ffd166;font-weight:700;background:#000000a0;"
                            "padding:1px 6px;border-radius:8px;")
        badge.setFixedSize(70, 18)
        # 缩略图占位
        self.thumb = QtWidgets.QLabel()
        self.thumb.setFixedSize(120, 160)
        self.thumb.setAlignment(QtCore.Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#2a2b2f;border-radius:6px;color:#666;")
        self.thumb.setText("加载中…")
        self.duration_lbl = QtWidgets.QLabel("")
        if duration_ms:
            secs = duration_ms // 1000
            self.duration_lbl.setText(f"{secs//60:02d}:{secs%60:02d}")
        self.duration_lbl.setStyleSheet("color:#aaa;font-size:11px;")
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
        d = str(HERE / "downloads")
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
        self.title_lbl.setStyleSheet("font-size:14px;font-weight:600;padding:4px 0;")
        root.addWidget(self.title_lbl)
        self.stats_lbl = QtWidgets.QLabel("")
        self.stats_lbl.setStyleSheet("color:#9aa0a6;font-size:12px;")
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
        self.status.showMessage(f"{APP_NAME} · 先运行 init_login.py 完成登录态")

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
    """首启自检 chromium；缺失则用 playwright 驱动自动安装(方案 A)。"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        return True
    except Exception:
        pass
    print("[*] chromium 未就绪，自动安装中(约 150MB，需联网)...")
    try:
        from playwright._impl._driver import compute_driver_executable
        import subprocess
        exe = compute_driver_executable()
        subprocess.run([exe, "install", "chromium"], check=False)
        # 再验一次
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            b.close()
        return True
    except Exception as e:
        print(f"[x] chromium 自动安装失败: {e}")
        print("    请手动运行: playwright install chromium")
        return False


def _check_login_hint():
    """profile 登录态自检并提示。"""
    try:
        from init_login import check_login, profile_path
        prof = profile_path()
        ok, msg = check_login(prof)
        return ok, msg, prof
    except Exception as e:
        return False, f"自检异常: {e}", None


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(QSS)
    ico = HERE / "app_icon.ico"
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
        QtWidgets.QMessageBox.information(w, "登录态",
            f"检测到登录态缺失:\n{msg}\n\n请先运行 init_login.py 完成登录，"
            f"否则喜欢列表/私密链接可能无法下载。")
        w.status.showMessage("未登录 —— 请先运行 init_login.py")
    else:
        w.status.showMessage(f"已就绪 · {msg}")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

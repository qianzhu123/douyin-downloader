"""生成 app_icon.ico —— 抖音下载器应用图标(深色蓝调，下载主题)。

不依赖外部素材：用 qt 渲染本地内联 SVG 为多尺寸 PNG，再 Pillow 合成 .ico。
图标为原始设计(蓝底圆角 + 白色下箭头/托盘)，规避第三方许可问题。

用法: python make_icon.py
输出: app_icon.ico, app_icon.png (供调试)
"""
from pathlib import Path
from PyQt5 import QtCore, QtGui, QtSvg, QtWidgets
from PIL import Image
import io

HERE = Path(__file__).resolve().parent
OUT_ICO = HERE / "app_icon.ico"
OUT_PNG = HERE / "app_icon.png"

SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3a9bff"/>
      <stop offset="1" stop-color="#2f6fd8"/>
    </linearGradient>
  </defs>
  <rect x="12" y="12" width="232" height="232" rx="52" fill="url(#g)"/>
  <!-- 向下箭头 -->
  <path d="M128 56 L128 156" stroke="#ffffff" stroke-width="22" stroke-linecap="round"/>
  <path d="M86 120 L128 168 L170 120" stroke="#ffffff" stroke-width="22" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <!-- 底部托盘 -->
  <path d="M72 184 L72 200 Q72 212 84 212 L172 212 Q184 212 184 200 L184 184"
        stroke="#ffffff" stroke-width="18" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>
"""

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(size: int) -> bytes:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(SVG.encode("utf-8")))
    if not renderer.isValid():
        raise RuntimeError("SVG 无效")
    img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
    img.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(img)
    renderer.render(painter)
    painter.end()
    buf = QtCore.QByteArray()
    ba = QtCore.QBuffer(buf)
    ba.open(QtCore.QIODevice.WriteOnly)
    img.save(ba, "PNG")
    return bytes(buf)


def main():
    big = render(256)
    OUT_PNG.write_bytes(big)
    # Pillow 会按 sizes 自动从大图下采样生成多尺寸 ICO 帧
    img = Image.open(io.BytesIO(big)).convert("RGBA")
    img.save(str(OUT_ICO), format="ICO",
            sizes=[(s, s) for s in SIZES])
    out = Image.open(str(OUT_ICO))
    print(f"[+] 写出: {OUT_ICO}  {OUT_ICO.stat().st_size} bytes  帧数={getattr(out,'n_frames',1)}")
    print(f"[+] 预览: {OUT_PNG}  {img.size}")


if __name__ == "__main__":
    main()

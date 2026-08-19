"""Khung xem trước: vẽ khung hình đã xử lý, giữ đúng tỉ lệ, có nền ca-rô khi trong suốt."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import style


def _checkerboard(size: int = 16) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(QColor("#2a2e38"))
    p = QPainter(pm)
    p.fillRect(0, 0, size, size, QColor("#343945"))
    p.fillRect(size, size, size, size, QColor("#343945"))
    p.end()
    return pm


class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAutoFillBackground(True)
        self._image: QImage | None = None
        self._buffer: np.ndarray | None = None     # giữ tham chiếu bộ nhớ cho QImage
        self._checker = _checkerboard()
        self._placeholder = "Đang chờ tín hiệu camera…"
        self._show_alpha = False

    # ---------- dữ liệu ----------
    def set_frame(self, rgb: np.ndarray, alpha: np.ndarray | None = None) -> None:
        h, w = rgb.shape[:2]
        if alpha is not None:
            buf = np.dstack([rgb, alpha])
            image = QImage(buf.data, w, h, 4 * w, QImage.Format_RGBA8888)
            self._show_alpha = True
        else:
            buf = np.ascontiguousarray(rgb)
            image = QImage(buf.data, w, h, 3 * w, QImage.Format_RGB888)
            self._show_alpha = False
        self._buffer = buf
        self._image = image
        self.update()

    def clear(self, message: str = "Đang chờ tín hiệu camera…") -> None:
        self._image = None
        self._buffer = None
        self._placeholder = message
        self.update()

    # ---------- vẽ ----------
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#0e1014"))

        if self._image is None:
            p.setPen(QPen(QColor(style.TEXT_DIM)))
            p.drawText(self.rect(), Qt.AlignCenter, self._placeholder)
            p.end()
            return

        target = self._fit_rect(self._image.width(), self._image.height())
        if self._show_alpha:
            p.setBrushOrigin(target.topLeft())
            p.fillRect(target, QBrush(self._checker))
        p.drawImage(target, self._image)

        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.drawRect(target.adjusted(0, 0, -1, -1))
        p.end()

    def _fit_rect(self, iw: int, ih: int) -> QRect:
        w, h = self.width(), self.height()
        if iw <= 0 or ih <= 0:
            return QRect(0, 0, w, h)
        scale = min(w / iw, h / ih)
        tw, th = int(iw * scale), int(ih * scale)
        return QRect((w - tw) // 2, (h - th) // 2, tw, th)

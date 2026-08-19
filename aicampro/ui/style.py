"""Bảng màu và stylesheet tối cho AICamPro.

Lưu ý: KHÔNG đặt `background` trong quy tắc `QWidget` chung. Qt sẽ áp nó cho mọi
widget con (QLabel, QSlider…), khiến chúng tự tô một hình chữ nhật tối đè lên nền
panel và làm hỏng kích thước các sub-control như groove/handle của slider.
Nền chỉ được đặt cho đúng những vùng chứa cần nó.
"""

import os
from pathlib import Path

BG = "#14161b"
PANEL = "#1b1e25"
PANEL_HI = "#232733"
BORDER = "#2c313d"
TEXT = "#e6e9ef"
TEXT_DIM = "#8b93a5"
ACCENT = "#ff6b4a"
ACCENT_DIM = "#c9482c"
TRACK_OFF = "#333947"
OK = "#3ecf8e"
WARN = "#f0b429"
ERR = "#ff5c5c"

def _arrow_icon() -> str:
    """Vẽ mũi tên xổ xuống ra file PNG và trả về đường dẫn.

    Qt QSS không hiểu mẹo tam giác bằng `border-left/right/top` của CSS — nó chỉ
    nhận `image: url(...)`. Vẽ sẵn bằng QPainter để khỏi phải kèm file ảnh vào repo.
    """
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QPolygonF

    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "aicampro"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "arrow-down.png"
    if not path.exists():
        scale = 2                      # vẽ ở 2x cho màn hình mật độ cao
        pm = QPixmap(10 * scale, 6 * scale)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(TEXT_DIM)))
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(10 * scale, 0),
                                 QPointF(5 * scale, 6 * scale)]))
        p.end()
        pm.save(str(path), "PNG")
    return path.as_posix()


def build_stylesheet() -> str:
    """Dựng stylesheet. Phải gọi sau khi đã tạo QApplication (cần vẽ icon)."""
    return _STYLESHEET_TEMPLATE.replace("@ARROW@", _arrow_icon())


_STYLESHEET_TEMPLATE = f"""
QWidget {{
    color: {TEXT};
    font-family: "Inter", "Ubuntu", "Noto Sans", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QLabel, QCheckBox {{ background: transparent; }}
QSlider {{ background: transparent; min-height: 18px; }}

/* ---- khung nhóm ---- */
#SectionHeader {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 10px;
    text-align: left;
    font-weight: 600;
    font-size: 13px;
}}
#SectionHeader:hover {{ background: {PANEL_HI}; }}
#SectionHeader:checked {{
    border-bottom-left-radius: 0; border-bottom-right-radius: 0;
    border-bottom: none;
}}
#SectionBody {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-top: none;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}}

/* ---- chữ ---- */
#Title {{ font-size: 19px; font-weight: 700; letter-spacing: 0.4px; }}
#Chip {{
    background: {PANEL_HI}; color: {TEXT_DIM};
    border: 1px solid {BORDER}; border-radius: 11px;
    padding: 3px 10px; font-size: 11px;
}}
#Hint {{ color: {TEXT_DIM}; font-size: 11px; }}
#ValueLabel {{ color: {TEXT_DIM}; font-size: 11px; min-width: 46px; }}
#RowLabel {{ color: {TEXT}; font-size: 12px; }}

/* ---- nút ---- */
QPushButton {{
    background: {PANEL_HI};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 12px;
    color: {TEXT};
}}
QPushButton:hover {{ background: #2b3040; border-color: #3a4152; }}
QPushButton:pressed {{ background: #191d27; }}
QPushButton:disabled {{ color: #565d6d; background: #1a1d24; }}
QPushButton#Accent {{
    background: {ACCENT}; border: none; color: #1a0d09; font-weight: 600;
}}
QPushButton#Accent:hover {{ background: #ff7f62; }}
QPushButton#Accent:pressed {{ background: {ACCENT_DIM}; }}
QPushButton#Danger {{ background: #3a1f1f; border-color: #5c2b2b; color: #ff9a9a; }}
QPushButton#Danger:hover {{ background: #4a2626; }}

/* ---- ô nhập / combo ---- */
QComboBox, QLineEdit, QSpinBox {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: {ACCENT};
}}
QComboBox:hover, QLineEdit:hover {{ border-color: #3a4152; }}
QComboBox::drop-down {{ border: none; width: 20px; background: transparent; }}
QComboBox::down-arrow {{
    image: url(@ARROW@);
    width: 10px; height: 6px;
    margin-right: 7px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL_HI};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    selection-color: #1a0d09;
    outline: none;
    padding: 3px;
}}

/* ---- slider ---- */
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
    margin: 0px;
}}
QSlider::sub-page:horizontal {{
    height: 4px; background: {ACCENT}; border-radius: 2px;
}}
QSlider::add-page:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    border: none;
    width: 14px; height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: #ffffff; }}
QSlider::handle:horizontal:disabled {{ background: #5a6070; }}
QSlider::sub-page:horizontal:disabled {{ background: #3a3f4c; }}

/* ---- vùng cuộn ---- */
QScrollArea {{ border: none; background: {BG}; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #363c4a; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #454c5e; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- linh tinh ---- */
QToolTip {{
    background: {PANEL_HI}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 5px; padding: 5px;
}}
#StatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}
#Separator {{ background: {BORDER}; border: none; max-height: 1px; min-height: 1px; }}
"""

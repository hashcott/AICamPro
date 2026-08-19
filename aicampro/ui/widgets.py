"""Widget dùng lại trong bảng điều khiển."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import style


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


class ToggleSwitch(QAbstractButton):
    """Công tắc trượt tự vẽ.

    QSS không tạo được núm trượt cho QCheckBox::indicator — chỉ đổi được màu nền,
    nên công tắc trông như một viên thuốc đặc, không rõ đang bật hay tắt.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(38, 21)
        self._knob = 0.0
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def getKnobPos(self) -> float:
        return self._knob

    def setKnobPos(self, value: float) -> None:
        self._knob = float(value)
        self.update()

    knobPos = Property(float, getKnobPos, setKnobPos)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        if not self._anim.state():
            self._knob = 1.0 if checked else 0.0
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        track = _blend(QColor(style.TRACK_OFF), QColor(style.ACCENT), self._knob)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)

        pad = 2.5
        d = r.height() - pad * 2
        x = r.left() + pad + self._knob * (r.width() - d - pad * 2)
        p.setBrush(QColor("#ffffff") if self._knob > 0.5 else QColor("#b9c0cf"))
        p.drawEllipse(QRectF(x, r.top() + pad, d, d))


class NoWheelMixin:
    """Chặn lăn chuột đổi giá trị khi người dùng chỉ đang cuộn bảng điều khiển.

    Chỉ nhận sự kiện wheel khi widget đang được focus (đã bấm vào).
    """

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SafeComboBox(NoWheelMixin, QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)


class SafeSlider(NoWheelMixin, QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setFocusPolicy(Qt.StrongFocus)


class Section(QWidget):
    """Nhóm thiết lập gập/mở được."""

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self.header = QPushButton(f"  {title}")
        self.header.setObjectName("SectionHeader")
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.toggled.connect(self._on_toggle)

        self.body = QFrame()
        self.body.setObjectName("SectionBody")
        self.form = QVBoxLayout(self.body)
        self.form.setContentsMargins(12, 10, 12, 12)
        self.form.setSpacing(9)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.header)
        outer.addWidget(self.body)
        self._title = title
        self._on_toggle(expanded)

    def _on_toggle(self, checked: bool) -> None:
        self.body.setVisible(checked)
        self.header.setText(("  ▾  " if checked else "  ▸  ") + self._title)

    def add(self, widget: QWidget) -> QWidget:
        self.form.addWidget(widget)
        return widget

    def add_row(self, *widgets: QWidget, spacing: int = 8) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(spacing)
        for w in widgets:
            lay.addWidget(w)
        self.form.addWidget(row)
        return row

    def add_hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Hint")
        label.setWordWrap(True)
        self.form.addWidget(label)
        return label


class SliderRow(QWidget):
    """Nhãn + thanh trượt + giá trị, làm việc với số thực."""

    valueChanged = Signal(float)

    def __init__(self, label: str, minimum: float, maximum: float, value: float,
                 decimals: int = 2, suffix: str = "", integer: bool = False, parent=None):
        super().__init__(parent)
        self._min, self._max = float(minimum), float(maximum)
        self._integer = integer
        self._decimals = 0 if integer else decimals
        self._suffix = suffix
        # với số nguyên, mỗi nấc trượt ứng đúng một giá trị (tối đa 2000 nấc)
        self._steps = int(min(2000, max(1, round(maximum - minimum)))) if integer else 1000

        self.label = QLabel(label)
        self.label.setObjectName("RowLabel")
        self.slider = SafeSlider(Qt.Horizontal)
        self.slider.setRange(0, self._steps)
        self.slider.setSingleStep(5)
        self.value_label = QLabel()
        self.value_label.setObjectName("ValueLabel")
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        top.addWidget(self.label, 1)
        top.addWidget(self.value_label, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addLayout(top)
        lay.addWidget(self.slider)

        self.slider.valueChanged.connect(self._on_slide)
        self.set_value(value)

    def _to_slider(self, v: float) -> int:
        span = self._max - self._min or 1.0
        return round((v - self._min) / span * self._steps)

    def _from_slider(self, i: int) -> float:
        v = self._min + (i / self._steps) * (self._max - self._min)
        return float(round(v)) if self._integer else v

    def _on_slide(self, i: int) -> None:
        v = self._from_slider(i)
        self.value_label.setText(f"{v:.{self._decimals}f}{self._suffix}")
        self.valueChanged.emit(v)

    def value(self) -> float:
        return self._from_slider(self.slider.value())

    def set_value(self, v: float) -> None:
        blocked = self.slider.blockSignals(True)
        self.slider.setValue(self._to_slider(float(v)))
        self.slider.blockSignals(blocked)
        self.value_label.setText(f"{float(v):.{self._decimals}f}{self._suffix}")

    def bind(self, fn: Callable[[float], None]) -> SliderRow:
        self.valueChanged.connect(fn)
        return self


class ToggleRow(QWidget):
    toggled = Signal(bool)

    def __init__(self, label: str, checked: bool = False, parent=None):
        super().__init__(parent)
        self.check = ToggleSwitch()
        self.check.setChecked(checked)
        text = QLabel(label)
        text.setObjectName("RowLabel")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(text, 1)
        lay.addWidget(self.check, 0)
        self.check.toggled.connect(self.toggled)

    def is_checked(self) -> bool:
        return self.check.isChecked()

    def set_checked(self, v: bool) -> None:
        blocked = self.check.blockSignals(True)
        self.check.setChecked(bool(v))
        self.check.blockSignals(blocked)

    def bind(self, fn: Callable[[bool], None]) -> ToggleRow:
        self.toggled.connect(fn)
        return self


class LabeledCombo(QWidget):
    changed = Signal(int)

    def __init__(self, label: str, items: list[str] | None = None, parent=None):
        super().__init__(parent)
        text = QLabel(label)
        text.setObjectName("RowLabel")
        self.combo = SafeComboBox()
        self.combo.setCursor(Qt.PointingHandCursor)
        if items:
            self.combo.addItems(items)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(text, 0)
        lay.addWidget(self.combo, 1)
        self.combo.currentIndexChanged.connect(self.changed)

    def set_items(self, items: list[str], data: list | None = None,
                  current=None) -> None:
        blocked = self.combo.blockSignals(True)
        self.combo.clear()
        for i, text in enumerate(items):
            self.combo.addItem(text, data[i] if data else text)
        if current is not None:
            self._select(current)
        self.combo.blockSignals(blocked)

    def _select(self, value) -> bool:
        """Chọn mục theo giá trị.

        Không dùng QComboBox.findData: với dữ liệu Python phức tạp (tuple…)
        Qt so sánh theo identity nên tuple dựng lúc chạy sẽ không bao giờ khớp.
        """
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == value:
                self.combo.setCurrentIndex(i)
                return True
        return False

    def set_current(self, value) -> bool:
        blocked = self.combo.blockSignals(True)
        found = self._select(value)
        self.combo.blockSignals(blocked)
        return found

    def data(self):
        return self.combo.currentData()

    def bind(self, fn) -> LabeledCombo:
        self.changed.connect(lambda _: fn(self.data()))
        return self


class ColorButton(QPushButton):
    colorChanged = Signal(tuple)

    def __init__(self, rgb: tuple, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        self._rgb = tuple(rgb)
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self) -> None:
        r, g, b = self._rgb
        fg = "#000" if (r * 0.299 + g * 0.587 + b * 0.114) > 150 else "#fff"
        self.setStyleSheet(
            f"background: rgb({r},{g},{b}); color: {fg};"
            f"border: 1px solid {style.BORDER}; border-radius: 6px; font-size: 11px;")
        self.setText(f"#{r:02X}{g:02X}{b:02X}")

    def _pick(self) -> None:
        color = QColorDialog.getColor(QColor(*self._rgb), self, "Chọn màu nền")
        if color.isValid():
            self.set_rgb((color.red(), color.green(), color.blue()))
            self.colorChanged.emit(self._rgb)

    def set_rgb(self, rgb: tuple) -> None:
        self._rgb = tuple(int(c) for c in rgb)
        self._refresh()


def separator() -> QWidget:
    line = QWidget()
    line.setObjectName("Separator")
    line.setFixedHeight(1)
    return line

"""Điều khiển phần cứng camera qua V4L2 (phơi sáng, gain, cân bằng trắng…).

Mở một file descriptor riêng chỉ để gọi ioctl điều khiển, nên dùng được song song
với luồng đang stream hình. Các thiết lập này do UVC lưu ngay trên camera và giữ
nguyên sau khi ứng dụng thoát — vì vậy luôn có nút đặt lại mặc định.
"""
from __future__ import annotations

import fcntl
import os
import struct
from dataclasses import dataclass

# _IOWR('V', nr, size)
VIDIOC_QUERYCTRL = (3 << 30) | (68 << 16) | (0x56 << 8) | 36
VIDIOC_G_CTRL = (3 << 30) | (8 << 16) | (0x56 << 8) | 27
VIDIOC_S_CTRL = (3 << 30) | (8 << 16) | (0x56 << 8) | 28

CTRL_FLAG_DISABLED = 0x0001
CTRL_FLAG_READ_ONLY = 0x0004

TYPE_INTEGER = 1
TYPE_BOOLEAN = 2
TYPE_MENU = 3

# chế độ phơi sáng của UVC
EXPOSURE_MANUAL = 1
EXPOSURE_APERTURE_PRIORITY = 3

# Danh sách chọn lọc: id, khoá, nhãn hiển thị.
# Thứ tự ở đây cũng là thứ tự hiện trên giao diện.
KNOWN_CONTROLS: list[tuple[int, str, str]] = [
    (0x009A0901, "exposure_auto", "Phơi sáng tự động"),
    (0x009A0902, "exposure_absolute", "Thời gian phơi sáng"),
    (0x009A0903, "exposure_auto_priority", "Cho phép giảm fps để đủ sáng"),
    (0x00980913, "gain", "Gain"),
    (0x00980900, "brightness", "Độ sáng"),
    (0x00980901, "contrast", "Tương phản (camera)"),
    (0x00980902, "saturation", "Bão hoà (camera)"),
    (0x0098091C, "backlight_compensation", "Bù ngược sáng"),
    (0x0098090C, "auto_white_balance", "Cân bằng trắng tự động"),
    (0x0098091A, "white_balance_temperature", "Nhiệt độ màu"),
    (0x0098091B, "sharpness", "Độ nét (camera)"),
]


@dataclass
class Control:
    id: int
    key: str
    label: str
    type: int
    minimum: int
    maximum: int
    step: int
    default: int
    value: int

    @property
    def is_bool(self) -> bool:
        return self.type == TYPE_BOOLEAN


class CameraControls:
    """Đọc/ghi control V4L2 của một thiết bị camera."""

    def __init__(self, device: str):
        self.device = device
        self._fd: int | None = None

    # ---------- vòng đời ----------
    def _open(self) -> int | None:
        if self._fd is None:
            try:
                self._fd = os.open(self.device, os.O_RDWR | os.O_NONBLOCK)
            except OSError:
                self._fd = None
        return self._fd

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self) -> "CameraControls":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ---------- truy vấn ----------
    def query(self, cid: int) -> tuple | None:
        """Trả về (type, min, max, step, default, flags) hoặc None nếu không hỗ trợ."""
        fd = self._open()
        if fd is None:
            return None
        buf = bytearray(68)
        struct.pack_into("<I", buf, 0, cid)
        try:
            fcntl.ioctl(fd, VIDIOC_QUERYCTRL, buf, True)
        except OSError:
            return None
        ctype = struct.unpack_from("<I", buf, 4)[0]
        minimum, maximum, step, default = struct.unpack_from("<iiii", buf, 40)
        flags = struct.unpack_from("<I", buf, 56)[0]
        return ctype, minimum, maximum, step, default, flags

    def get(self, cid: int) -> int | None:
        fd = self._open()
        if fd is None:
            return None
        buf = bytearray(8)
        struct.pack_into("<I", buf, 0, cid)
        try:
            fcntl.ioctl(fd, VIDIOC_G_CTRL, buf, True)
        except OSError:
            return None
        return struct.unpack_from("<i", buf, 4)[0]

    def set(self, cid: int, value: int) -> bool:
        fd = self._open()
        if fd is None:
            return False
        buf = bytearray(8)
        struct.pack_into("<Ii", buf, 0, cid, int(value))
        try:
            fcntl.ioctl(fd, VIDIOC_S_CTRL, buf, True)
            return True
        except OSError:
            return False

    # ---------- mức cao ----------
    def available(self) -> list[Control]:
        out: list[Control] = []
        for cid, key, label in KNOWN_CONTROLS:
            info = self.query(cid)
            if info is None:
                continue
            ctype, minimum, maximum, step, default, flags = info
            if flags & (CTRL_FLAG_DISABLED | CTRL_FLAG_READ_ONLY):
                continue
            if ctype not in (TYPE_INTEGER, TYPE_BOOLEAN, TYPE_MENU):
                continue
            value = self.get(cid)
            if value is None:
                continue
            out.append(Control(cid, key, label, ctype, minimum, maximum,
                               max(1, step), default, value))
        return out

    def reset_defaults(self) -> int:
        """Đưa mọi control về giá trị mặc định của camera. Trả về số control đã đổi."""
        changed = 0
        # đặt các chế độ 'tự động' sau cùng: bật auto sẽ khoá control thủ công tương ứng
        controls = self.available()
        manual_first = sorted(controls, key=lambda c: c.key.startswith(("exposure_auto",
                                                                       "auto_white")))
        for c in manual_first:
            if c.value != c.default and self.set(c.id, c.default):
                changed += 1
        return changed

    def auto_exposure_on(self) -> bool:
        """Bật lại phơi sáng tự động — cách nhanh nhất khi hình bị tối/cháy sáng."""
        return self.set(0x009A0901, EXPOSURE_APERTURE_PRIORITY)

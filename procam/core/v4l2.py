"""Truy vấn thiết bị V4L2 trực tiếp qua ioctl — không cần v4l-utils."""
from __future__ import annotations

import fcntl
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path

# _IOC(dir, 'V', nr, size) — dir: 2 = _IOR (đọc ra), 3 = _IOWR (ghi vào rồi đọc ra)
def _ioc(direction: int, nr: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (0x56 << 8) | nr


VIDIOC_QUERYCAP = _ioc(2, 0, 104)          # _IOR('V', 0, struct v4l2_capability)
VIDIOC_ENUM_FRAMESIZES = _ioc(3, 74, 44)   # _IOWR('V', 74, struct v4l2_frmsizeenum)

CAP_VIDEO_CAPTURE = 0x00000001
CAP_VIDEO_OUTPUT = 0x00000002
CAP_DEVICE_CAPS = 0x80000000

FRMSIZE_DISCRETE = 1


def fourcc(code: str) -> int:
    b = code.ljust(4)[:4].encode()
    return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)


@dataclass
class V4L2Device:
    path: str
    name: str
    driver: str
    is_capture: bool
    is_output: bool
    virtual: bool = False
    sizes: list[tuple[int, int]] = field(default_factory=list)

    @property
    def is_virtual(self) -> bool:
        return self.virtual or "loopback" in self.driver

    @property
    def can_output(self) -> bool:
        """Thiết bị có thực sự nhận được luồng ghi vào không.

        Thiết bị v4l2loopback dựng bằng `exclusive_caps=1` mà chưa từng được
        thương lượng định dạng có thể không khai báo cả CAPTURE lẫn OUTPUT —
        lúc đó không ứng dụng nào ghi vào được, kể cả ffmpeg.
        """
        return self.is_output

    @property
    def label(self) -> str:
        suffix = "" if not self.is_virtual or self.can_output else "  — không ghi được"
        return f"{self.name} ({self.path}){suffix}"


def _sysfs_name(node: str) -> str:
    try:
        return (Path("/sys/class/video4linux") / node / "name").read_text().strip()
    except OSError:
        return node


def _is_virtual_node(node: str) -> bool:
    """Thiết bị ảo (v4l2loopback) nằm dưới /sys/devices/virtual/ — đọc được mà
    không cần mở thiết bị, tránh làm lật trạng thái của node loopback."""
    try:
        return "/devices/virtual/" in str((Path("/sys/class/video4linux") / node).resolve())
    except OSError:
        return False


def _query(path: str) -> V4L2Device | None:
    node = Path(path).name
    virtual = _is_virtual_node(node)
    # thiết bị loopback: mở bằng O_RDWR đúng như ứng dụng ghi vào sẽ làm
    flags = os.O_RDWR if virtual else (os.O_RDONLY | os.O_NONBLOCK)
    try:
        fd = os.open(path, flags)
    except OSError:
        if virtual:
            return V4L2Device(path=path, name=_sysfs_name(node), driver="v4l2 loopback",
                              is_capture=False, is_output=False, virtual=True)
        return None
    try:
        buf = bytearray(104)
        fcntl.ioctl(fd, VIDIOC_QUERYCAP, buf, True)
        driver = buf[0:16].split(b"\0")[0].decode(errors="replace")
        card = buf[16:48].split(b"\0")[0].decode(errors="replace")
        caps, device_caps = struct.unpack_from("<II", buf, 84)
        effective = device_caps if caps & CAP_DEVICE_CAPS else caps
        dev = V4L2Device(
            path=path,
            name=card or _sysfs_name(node),
            driver=driver,
            is_capture=bool(effective & CAP_VIDEO_CAPTURE),
            is_output=bool(effective & CAP_VIDEO_OUTPUT),
            virtual=virtual,
        )
        if dev.is_capture and not virtual:
            dev.sizes = _frame_sizes(fd)
        return dev
    except OSError:
        return None
    finally:
        os.close(fd)


def _frame_sizes(fd: int) -> list[tuple[int, int]]:
    found: set[tuple[int, int]] = set()
    for fmt in ("MJPG", "YUYV", "NV12"):
        pf = fourcc(fmt)
        for index in range(64):
            buf = bytearray(44)
            struct.pack_into("<II", buf, 0, index, pf)
            try:
                fcntl.ioctl(fd, VIDIOC_ENUM_FRAMESIZES, buf, True)
            except OSError:
                break
            ftype = struct.unpack_from("<I", buf, 8)[0]
            if ftype != FRMSIZE_DISCRETE:
                break
            w, h = struct.unpack_from("<II", buf, 12)
            if 160 <= w <= 7680 and 120 <= h <= 4320:
                found.add((w, h))
    return sorted(found, key=lambda s: (s[0] * s[1]), reverse=True)


def enumerate_devices() -> list[V4L2Device]:
    paths = sorted(
        (p for p in Path("/dev").glob("video*") if p.name[5:].isdigit()),
        key=lambda p: int(p.name[5:]),
    )
    out: list[V4L2Device] = []
    for p in paths:
        dev = _query(str(p))
        if dev is not None:
            out.append(dev)
    return out


def capture_devices() -> list[V4L2Device]:
    """Camera thật (bỏ node metadata và thiết bị ảo)."""
    return [d for d in enumerate_devices() if d.is_capture and d.sizes and not d.is_virtual]


def loopback_devices() -> list[V4L2Device]:
    """Thiết bị v4l2loopback dùng làm webcam ảo đầu ra, cái ghi được xếp trước."""
    devs = [d for d in enumerate_devices() if d.is_virtual or (d.is_output and not d.sizes)]
    return sorted(devs, key=lambda d: (not d.can_output, d.path))


def writable_loopback_devices() -> list[V4L2Device]:
    return [d for d in loopback_devices() if d.can_output]

"""Số hiệu ioctl V4L2 phải khớp giá trị kernel định nghĩa. Không cần GPU.

Sai một bit trong chiều hoặc kích thước struct là ioctl trả ENOTTY và mọi thứ
liên quan tới thiết bị hỏng lặng lẽ. Những hằng số này đã sai một lần
(VIDIOC_QUERYCAP dùng nhầm _IOWR thay vì _IOR) nên khoá chúng lại.
"""
from __future__ import annotations

from aicampro.core import camera_controls as cc
from aicampro.core import v4l2

# Giá trị trên x86_64, đối chiếu <linux/videodev2.h>
KERNEL_VALUES = {
    "VIDIOC_QUERYCAP": 0x80685600,
    "VIDIOC_ENUM_FRAMESIZES": 0xC02C564A,
    "VIDIOC_G_CTRL": 0xC008561B,
    "VIDIOC_S_CTRL": 0xC008561C,
    "VIDIOC_QUERYCTRL": 0xC0445624,
}


def test_v4l2_ioctl_numbers():
    assert KERNEL_VALUES["VIDIOC_QUERYCAP"] == v4l2.VIDIOC_QUERYCAP
    assert KERNEL_VALUES["VIDIOC_ENUM_FRAMESIZES"] == v4l2.VIDIOC_ENUM_FRAMESIZES


def test_camera_control_ioctl_numbers():
    assert KERNEL_VALUES["VIDIOC_G_CTRL"] == cc.VIDIOC_G_CTRL
    assert KERNEL_VALUES["VIDIOC_S_CTRL"] == cc.VIDIOC_S_CTRL
    assert KERNEL_VALUES["VIDIOC_QUERYCTRL"] == cc.VIDIOC_QUERYCTRL


def test_fourcc_packing():
    assert v4l2.fourcc("MJPG") == 0x47504A4D
    assert v4l2.fourcc("YUYV") == 0x56595559
    assert v4l2.fourcc("RGB3") == 0x33424752


def test_enumeration_does_not_crash_without_devices():
    # Trên máy CI không có /dev/video* — phải trả danh sách rỗng, không nổ.
    assert isinstance(v4l2.enumerate_devices(), list)
    assert isinstance(v4l2.capture_devices(), list)
    assert isinstance(v4l2.loopback_devices(), list)

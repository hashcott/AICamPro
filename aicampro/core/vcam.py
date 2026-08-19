"""Xuất stream đã xử lý ra webcam ảo qua v4l2loopback."""
from __future__ import annotations

import numpy as np

from . import v4l2


class VirtualCameraError(RuntimeError):
    pass


class VirtualCamera:
    """Bọc pyvirtualcam, tự mở lại khi đổi kích thước/thiết bị."""

    def __init__(self):
        self._cam = None
        self._key: tuple | None = None
        self.device: str = ""

    @staticmethod
    def available_devices() -> list[v4l2.V4L2Device]:
        return v4l2.loopback_devices()

    @staticmethod
    def writable_devices() -> list[v4l2.V4L2Device]:
        return v4l2.writable_loopback_devices()

    def _open(self, width: int, height: int, fps: int, device: str) -> None:
        try:
            import pyvirtualcam
        except ImportError as exc:
            raise VirtualCameraError("Thiếu gói pyvirtualcam (pip install pyvirtualcam)") from exc

        if not device:
            usable = self.writable_devices()
            if usable:
                device = usable[0].path
            else:
                existing = self.available_devices()
                if existing:
                    names = ", ".join(d.path for d in existing)
                    raise VirtualCameraError(
                        f"Có thiết bị v4l2loopback ({names}) nhưng không cái nào nhận "
                        "được luồng ghi vào — thường do thiết bị của ứng dụng khác "
                        "(OBS…) dựng với exclusive_caps và đang kẹt trạng thái.\n"
                        "Tạo thiết bị riêng cho AICamPro:\n"
                        "  sudo ./scripts/setup_v4l2loopback.sh"
                    )
                raise VirtualCameraError(
                    "Không tìm thấy thiết bị v4l2loopback.\n"
                    "Chạy: sudo ./scripts/setup_v4l2loopback.sh"
                )

        self.close()
        try:
            self._cam = pyvirtualcam.Camera(
                width=width, height=height, fps=max(1, fps),
                device=device, fmt=pyvirtualcam.PixelFormat.RGB,
                print_fps=False,
            )
        except Exception as exc:
            hint = ""
            if "not a video output" in str(exc).lower():
                hint = ("\nThiết bị này không khai báo khả năng nhận luồng ghi vào.\n"
                        "Tạo thiết bị riêng cho AICamPro:  sudo ./scripts/setup_v4l2loopback.sh")
            raise VirtualCameraError(
                f"Không mở được webcam ảo {device}: {exc}{hint}") from exc
        self.device = device
        self._key = (width, height, int(fps), device)

    def send(self, rgb: np.ndarray, fps: int = 30, device: str = "") -> None:
        """rgb: mảng uint8 (H, W, 3)."""
        h, w = rgb.shape[:2]
        key = (w, h, int(fps), device or self.device)
        if self._cam is None or self._key != key:
            self._open(w, h, fps, device)
        self._cam.send(rgb)

    def close(self) -> None:
        if self._cam is not None:
            try:
                self._cam.close()
            except Exception:
                pass
        self._cam = None
        self._key = None

    @property
    def is_open(self) -> bool:
        return self._cam is not None

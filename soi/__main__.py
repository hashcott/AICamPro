"""Điểm khởi chạy Soi."""
from __future__ import annotations

import argparse
import os
import sys


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="soi",
        description="Soi — xoá nền, filter và webcam ảo, tăng tốc bằng GPU AMD.")
    p.add_argument("--device", help="Đường dẫn camera, ví dụ /dev/video0")
    p.add_argument("--config", help="File cấu hình JSON thay cho mặc định")
    p.add_argument("--list-devices", action="store_true",
                   help="Liệt kê camera và thiết bị v4l2loopback rồi thoát")
    p.add_argument("--check", action="store_true",
                   help="Kiểm tra GPU/model/thiết bị rồi thoát")
    return p.parse_args(argv)


def _list_devices() -> int:
    from .core import v4l2
    cams = v4l2.capture_devices()
    print("Camera:")
    for d in cams or []:
        top = ", ".join(f"{w}×{h}" for w, h in d.sizes[:6])
        print(f"  {d.path:15} {d.name}\n{'':17} {top}")
    if not cams:
        print("  (không có)")
    print("\nWebcam ảo (v4l2loopback):")
    loops = v4l2.loopback_devices()
    for d in loops or []:
        mark = "✓ ghi được" if d.can_output else "✗ KHÔNG ghi được"
        print(f"  {d.path:15} {d.name:26} {mark}")
    if not loops:
        print("  (không có)")
    if not any(d.can_output for d in loops):
        print("  → Chưa có thiết bị dùng được. Chạy: sudo ./scripts/setup_v4l2loopback.sh")
    return 0


def _check() -> int:
    from .gpu import device as gpu_device
    from .gpu import segmentation as seg
    info = gpu_device.detect()
    print(f"Thiết bị tính toán : {info.summary()}")
    if not info.is_gpu:
        print("  ⚠ Không thấy GPU qua ROCm — Soi sẽ chạy trên CPU (rất chậm).")
    models = seg.available_models()
    print(f"Model tách nền     : {', '.join(models) if models else '(chưa có)'}")
    if not models:
        print("  ⚠ Chạy ./scripts/download_models.sh để tải model.")
    _list_devices()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.list_devices:
        return _list_devices()
    if args.check:
        return _check()

    # Qt trên Wayland đôi khi không dựng được cửa sổ với plugin mặc định
    os.environ.setdefault("QT_QPA_PLATFORM",
                          "wayland" if os.environ.get("WAYLAND_DISPLAY") else "xcb")

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .config import AppConfig
    from .ui.main_window import MainWindow
    from .ui.style import build_stylesheet

    cfg = AppConfig.load(args.config)
    if args.device:
        cfg.capture.device = args.device

    QApplication.setAttribute(Qt.AA_DontUseNativeMenuBar, False)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Soi")
    app.setApplicationDisplayName("Soi")
    app.setWindowIcon(QIcon())
    app.setStyleSheet(build_stylesheet())

    window = MainWindow(cfg)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

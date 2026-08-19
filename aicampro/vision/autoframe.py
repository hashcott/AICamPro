"""Tự động bám chủ thể: cắt/phóng khung hình theo người trong ảnh."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from ..config import MODEL_DIR, AutoFrameConfig

Box = tuple[float, float, float, float]      # (cx, cy, w, h) chuẩn hoá 0..1


class FaceTracker:
    """YuNet nếu có model, ngược lại dùng Haar cascade đi kèm OpenCV."""

    def __init__(self, every_n: int = 3):
        import cv2
        self.cv2 = cv2
        self.every_n = every_n
        self._tick = 0
        self._last: list[Box] = []
        self._yunet = None
        self._haar = None
        self._size = (0, 0)

        onnx = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
        if onnx.exists() and hasattr(cv2, "FaceDetectorYN"):
            try:
                self._yunet = cv2.FaceDetectorYN.create(str(onnx), "", (320, 240), 0.75, 0.3, 500)
            except Exception:
                self._yunet = None
        if self._yunet is None:
            cascade = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            if cascade.exists():
                self._haar = cv2.CascadeClassifier(str(cascade))

    @property
    def available(self) -> bool:
        return self._yunet is not None or self._haar is not None

    def detect(self, bgr: np.ndarray) -> list[Box]:
        self._tick += 1
        if self._tick % self.every_n != 1 and self._last:
            return self._last

        h, w = bgr.shape[:2]
        scale = 320.0 / max(1, w)
        small = self.cv2.resize(bgr, (int(w * scale), int(h * scale)))
        sh, sw = small.shape[:2]
        boxes: list[Box] = []

        if self._yunet is not None:
            if self._size != (sw, sh):
                self._yunet.setInputSize((sw, sh))
                self._size = (sw, sh)
            _, faces = self._yunet.detect(small)
            if faces is not None:
                for f in faces:
                    x, y, bw, bh = f[:4]
                    boxes.append(((x + bw / 2) / sw, (y + bh / 2) / sh, bw / sw, bh / sh))
        elif self._haar is not None:
            gray = self.cv2.cvtColor(small, self.cv2.COLOR_BGR2GRAY)
            for (x, y, bw, bh) in self._haar.detectMultiScale(gray, 1.2, 5, minSize=(30, 30)):
                boxes.append(((x + bw / 2) / sw, (y + bh / 2) / sh, bw / sw, bh / sh))

        self._last = boxes
        return boxes


def mask_box(alpha: torch.Tensor, threshold: float = 0.45) -> Box | None:
    """Hộp bao chủ thể lấy từ alpha (tính trên bản thu nhỏ cho rẻ)."""
    small = F.interpolate(alpha, size=(72, 128), mode="area")
    hit = (small > threshold).float()
    rows = hit.amax(dim=3).flatten()          # (72,)
    cols = hit.amax(dim=2).flatten()          # (128,)
    r = rows.detach().to("cpu").numpy()
    c = cols.detach().to("cpu").numpy()
    ry, cx = np.flatnonzero(r), np.flatnonzero(c)
    if ry.size < 2 or cx.size < 2:
        return None
    y0, y1 = ry[0] / 72.0, (ry[-1] + 1) / 72.0
    x0, x1 = cx[0] / 128.0, (cx[-1] + 1) / 128.0
    return ((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)


def resize_to(x: torch.Tensor | None, oh: int, ow: int) -> torch.Tensor | None:
    """Đổi kích thước với thuật toán hợp với hướng: bicubic khi phóng, area khi thu."""
    if x is None:
        return None
    h, w = x.shape[-2:]
    if (h, w) == (oh, ow):
        return x
    if oh * ow > h * w:
        out = F.interpolate(x, size=(oh, ow), mode="bicubic", align_corners=False)
        return out.clamp(0, 1)
    return F.interpolate(x, size=(oh, ow), mode="area")


class AutoFramer:
    def __init__(self):
        self._state: Box | None = None
        self._tracker: FaceTracker | None = None

    def reset(self) -> None:
        self._state = None

    def _face_tracker(self) -> FaceTracker:
        if self._tracker is None:
            self._tracker = FaceTracker()
        return self._tracker

    # ---------- chọn mục tiêu ----------
    def _target(self, cfg: AutoFrameConfig, alpha: torch.Tensor | None,
                bgr: np.ndarray | None) -> Box | None:
        source = cfg.source
        if source in ("auto", "mask") and alpha is not None:
            box = mask_box(alpha)
            if box is not None:
                return box
            if source == "mask":
                return None
        if source in ("auto", "face") and bgr is not None:
            tracker = self._face_tracker()
            if tracker.available:
                faces = tracker.detect(bgr)
                if faces:
                    # ưu tiên khuôn mặt lớn nhất, mở rộng xuống dưới để lấy nửa thân
                    cx, cy, w, h = max(faces, key=lambda b: b[2] * b[3])
                    return (cx, cy + h * 0.9, w * 3.2, h * 4.0)
        return None

    # ---------- hình học ----------
    @staticmethod
    def _crop_size(h: int, w: int, aspect: float, want_h_px: float) -> tuple[int, int]:
        """Kích thước khung cắt đúng tỉ lệ `aspect`, kẹp trong khung nguồn."""
        max_ch = min(h, w / aspect)
        ch = max(16.0, min(max_ch, want_h_px))
        return int(round(ch * aspect)), int(round(ch))

    def _crop_and_resize(self, image: torch.Tensor, alpha: torch.Tensor | None,
                         x0: int, y0: int, cw: int, ch: int, oh: int, ow: int):
        h, w = image.shape[-2:]
        x0 = min(max(0, x0), max(0, w - cw))
        y0 = min(max(0, y0), max(0, h - ch))
        cropped = image[..., y0:y0 + ch, x0:x0 + cw]
        out_alpha = None
        if alpha is not None:
            out_alpha = resize_to(alpha[..., y0:y0 + ch, x0:x0 + cw], oh, ow)
        return resize_to(cropped, oh, ow), out_alpha

    # ---------- áp dụng ----------
    def apply(self, image: torch.Tensor, cfg: AutoFrameConfig,
              alpha: torch.Tensor | None, bgr: np.ndarray | None,
              out_size: tuple[int, int] | None = None
              ) -> tuple[torch.Tensor, torch.Tensor | None]:
        """Cắt/phóng theo chủ thể rồi đưa về đúng `out_size` (cao, rộng).

        Khung cắt luôn giữ đúng tỉ lệ của đầu ra nên ảnh không bao giờ bị méo.
        """
        h, w = image.shape[-2:]
        oh, ow = out_size if out_size else (h, w)
        aspect = ow / oh

        if not cfg.enabled:
            self._state = None
            if (h, w) == (oh, ow):
                return image, alpha
            # cắt giữa theo tỉ lệ đầu ra rồi thu nhỏ — không kéo giãn
            cw, ch = self._crop_size(h, w, aspect, float(h))
            return self._crop_and_resize(image, alpha, (w - cw) // 2, (h - ch) // 2,
                                         cw, ch, oh, ow)

        target = self._target(cfg, alpha, bgr)
        if target is None and self._state is None:
            return self.apply(image, AutoFrameConfig(enabled=False), alpha, bgr, out_size)

        if target is not None:
            if self._state is None:
                self._state = target
            else:
                k = min(0.99, max(0.0, cfg.smoothing))
                self._state = tuple(
                    s * k + t * (1 - k) for s, t in zip(self._state, target)
                )                                             # type: ignore[assignment]

        assert self._state is not None
        cx, cy, bw, bh = self._state
        pad = max(1.0, cfg.zoom)

        # chiều cao khung cắt (px) đủ bao chủ thể ở cả hai trục
        want_h = max(bh * h * pad, (bw * w * pad) / aspect)
        # giới hạn phóng: so với khung lớn nhất cùng tỉ lệ lọt trong nguồn
        full_h = min(h, w / aspect)
        want_h = max(want_h, full_h / max(1.0, cfg.max_zoom))
        cw, ch = self._crop_size(h, w, aspect, want_h)

        x0 = int(round(cx * w - cw / 2))
        y0 = int(round(cy * h - ch / 2))
        return self._crop_and_resize(image, alpha, x0, y0, cw, ch, oh, ow)

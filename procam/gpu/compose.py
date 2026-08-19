"""Ghép chủ thể lên nền mới: làm mờ, thay ảnh, màu đặc, phông xanh, nền trong suốt."""
from __future__ import annotations


import numpy as np
import torch

from ..config import BackgroundConfig, resolve_asset
from . import ops


class BackgroundCompositor:
    def __init__(self, device: str):
        self.device = device
        self._image: torch.Tensor | None = None      # (1,3,H,W) gốc
        self._image_path = ""
        self._fitted: torch.Tensor | None = None     # cache đã fit đúng khung
        self._fitted_key: tuple | None = None

    # ---------- ảnh nền ----------
    def set_image(self, path: str) -> str | None:
        path = path or ""
        if path == self._image_path:
            return None
        if not path:
            self._image, self._image_path, self._fitted = None, "", None
            return None
        try:
            import cv2
            resolved = resolve_asset(path)
            if resolved is None:
                raise ValueError(f"Không tìm thấy ảnh nền: {path}")
            data = cv2.imread(str(resolved), cv2.IMREAD_COLOR)
            if data is None:
                raise ValueError(f"Không đọc được ảnh: {path}")
            rgb = cv2.cvtColor(data, cv2.COLOR_BGR2RGB)
            t = torch.from_numpy(np.ascontiguousarray(rgb)).to(self.device)
            self._image = (t.permute(2, 0, 1).unsqueeze(0).float() / 255.0)
            self._image_path = path
            self._fitted = None
            return None
        except (OSError, ValueError) as exc:
            self._image, self._image_path, self._fitted = None, "", None
            return str(exc)

    def _background_for(self, fg: torch.Tensor, cfg: BackgroundConfig) -> torch.Tensor:
        h, w = fg.shape[-2:]
        if cfg.mode == "image" and self._image is not None:
            key = (h, w, cfg.image_fit, self._image_path)
            if self._fitted_key != key:
                self._fitted = ops.resize_cover(self._image, h, w, cfg.image_fit)
                self._fitted_key = key
            return self._fitted
        rgb = cfg.green if cfg.mode == "greenscreen" else cfg.color
        color = torch.tensor([c / 255.0 for c in rgb], device=fg.device,
                             dtype=fg.dtype).view(1, 3, 1, 1)
        return color.expand(1, 3, h, w)

    # ---------- ghép ----------
    def compose(self, frame: torch.Tensor, alpha: torch.Tensor | None,
                fgr: torch.Tensor | None, cfg: BackgroundConfig) -> torch.Tensor:
        """Ghép chủ thể lên nền mới. Alpha đầu ra do pipeline xử lý riêng."""
        if cfg.mode == "none" or alpha is None:
            return frame

        # RVM trả về foreground đã khử viền màu nền — dùng nó cho biên sạch hơn
        subject = fgr if fgr is not None else frame

        if cfg.mode == "transparent":
            return subject

        if cfg.mode == "blur":
            # sigma tỉ lệ theo chiều rộng để mức mờ ổn định ở mọi độ phân giải
            sigma = 0.5 + cfg.blur * frame.shape[-1] / 32.0
            bg = ops.fast_blur(frame, sigma)
        else:
            bg = self._background_for(frame, cfg)

        return (subject * alpha + bg * (1.0 - alpha)).clamp(0, 1)

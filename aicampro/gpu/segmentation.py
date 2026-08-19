"""Tách nền (matting) chạy trên GPU AMD qua PyTorch/ROCm.

Backend chính: RobustVideoMatting (RVM) bản TorchScript — mạng hồi tiếp nên
alpha ổn định theo thời gian, không nhấp nháy như model tách theo từng khung.
"""
from __future__ import annotations

import contextlib
import threading
from pathlib import Path

import torch

from ..config import MODEL_DIR
from . import ops

# Bảng model tải kèm scripts/download_models.sh
KNOWN_MODELS = {
    "rvm_mobilenetv3_fp32": "Nhanh — khuyến nghị cho webcam thời gian thực",
    "rvm_mobilenetv3_fp16": "Nhanh + fp16 — nhẹ VRAM nhất",
    "rvm_resnet50_fp32": "Chất lượng biên tóc tốt hơn, nặng hơn ~3x",
    "rvm_resnet50_fp16": "resnet50 ở fp16",
}


def available_models() -> list[str]:
    if not MODEL_DIR.exists():
        return []
    return sorted(p.stem for p in MODEL_DIR.glob("*.torchscript"))


class Matter:
    """Giao diện chung cho mọi backend tách nền."""

    name = "none"

    def alpha(self, rgb: torch.Tensor) -> tuple[torch.Tensor | None, torch.Tensor | None]:
        """Trả về (alpha (1,1,H,W) 0..1, foreground đã khử viền màu hoặc None)."""
        raise NotImplementedError

    def configure(self, downsample: float = 0.0) -> None:
        """Nhận tham số chạy từ cấu hình. Backend nào không cần thì bỏ qua."""

    def reset(self) -> None:
        pass

    def close(self) -> None:
        pass


class NullMatter(Matter):
    def alpha(self, rgb):
        return None, None


class RVMMatter(Matter):
    """RobustVideoMatting TorchScript.

    Chữ ký model: (src, r1, r2, r3, r4, downsample_ratio)
                -> (fgr, pha, r1, r2, r3, r4)
    """

    name = "rvm"

    def __init__(self, model_path: Path, device: str, downsample: float = 0.0):
        self.path = Path(model_path)
        self.device = device
        self.half = "fp16" in self.path.stem and device != "cpu"
        self.dtype = torch.float16 if self.half else torch.float32
        self.downsample = downsample
        self._rec: list = [None] * 4
        self._last_shape: tuple | None = None
        self._lock = threading.Lock()

        model = torch.jit.load(str(self.path), map_location=device)
        model.eval()
        # freeze không bắt buộc; một số bản torch từ chối module đã freeze
        with contextlib.suppress(Exception):
            model = torch.jit.freeze(model)
        self.model = model

    # -- helper ---------------------------------------------------------
    def _ratio_for(self, h: int, w: int) -> float:
        if self.downsample > 0:
            return float(self.downsample)
        # RVM khuyến nghị cạnh dài sau khi thu nhỏ nằm quanh 512 px
        return float(min(1.0, max(0.125, 512.0 / max(h, w))))

    def configure(self, downsample: float = 0.0) -> None:
        self.downsample = downsample

    def reset(self) -> None:
        with self._lock:
            self._rec = [None] * 4
            self._last_shape = None

    # -- inference ------------------------------------------------------
    @torch.inference_mode()
    def alpha(self, rgb: torch.Tensor):
        h, w = rgb.shape[-2:]
        with self._lock:
            if self._last_shape != (h, w):
                self._rec = [None] * 4
                self._last_shape = (h, w)

            src, orig = ops.pad_to_multiple(rgb.to(self.dtype), 8)
            ratio = self._ratio_for(*src.shape[-2:])
            out = self.model(src, *self._rec, ratio)
            fgr, pha = out[0], out[1]
            self._rec = list(out[2:6])

        pha = ops.unpad(pha, orig).float()
        fgr = ops.unpad(fgr, orig).float().clamp(0, 1)
        return pha, fgr


def create_matter(model_name: str, device: str, downsample: float = 0.0) -> Matter:
    """Tạo backend tách nền; nếu thiếu model thì trả về NullMatter (chế độ bỏ qua)."""
    path = MODEL_DIR / f"{model_name}.torchscript"
    if not path.exists():
        candidates = available_models()
        if not candidates:
            raise FileNotFoundError(
                f"Không tìm thấy model tách nền trong {MODEL_DIR}.\n"
                f"Chạy: ./scripts/download_models.sh"
            )
        path = MODEL_DIR / f"{candidates[0]}.torchscript"
    return RVMMatter(path, device, downsample)


def refine_alpha(pha: torch.Tensor, feather: float, shift: float, contrast: float) -> torch.Tensor:
    """Hậu xử lý alpha: co/nở biên, làm mềm, tăng độ dứt khoát."""
    if abs(shift) > 0.01:
        radius = max(1, round(abs(shift) * 6))
        pha = ops.dilate(pha, radius) if shift > 0 else ops.erode(pha, radius)
    if contrast > 0.01:
        # đẩy alpha về 0/1 quanh ngưỡng 0.5
        k = 1.0 + contrast * 12.0
        pha = torch.sigmoid((pha - 0.5) * k * 2.0)
    if feather > 0.05:
        pha = ops.gaussian_blur(pha, feather)
    return pha.clamp(0, 1)

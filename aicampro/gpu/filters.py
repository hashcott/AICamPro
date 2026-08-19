"""Bộ lọc màu và làm đẹp, toàn bộ chạy trên GPU."""
from __future__ import annotations

import torch

from ..config import BeautyConfig, FilterConfig, resolve_asset
from . import ops
from .lut import CubeLUT, apply_lut


class FilterStack:
    """Giữ trạng thái nặng (LUT đã nạp) giữa các khung hình."""

    def __init__(self, device: str):
        self.device = device
        self._lut: CubeLUT | None = None
        self._lut_path: str = ""

    # ---------- LUT ----------
    def set_lut(self, path: str) -> str | None:
        """Nạp LUT mới. Trả về thông báo lỗi nếu thất bại, None nếu OK."""
        path = path or ""
        if path == self._lut_path:
            return None
        if not path:
            self._lut, self._lut_path = None, ""
            return None
        try:
            resolved = resolve_asset(path)
            if resolved is None:
                raise ValueError(f"Không tìm thấy LUT: {path}")
            self._lut = CubeLUT.load(resolved).to(self.device)
            self._lut_path = path
            return None
        except (OSError, ValueError) as exc:
            self._lut, self._lut_path = None, ""
            return str(exc)

    # ---------- màu ----------
    def apply_color(self, x: torch.Tensor, cfg: FilterConfig) -> torch.Tensor:
        if cfg.exposure:
            x = x * (2.0 ** (cfg.exposure * 1.5))
        if cfg.temperature or cfg.tint:
            gain = torch.tensor(
                [1.0 + cfg.temperature * 0.28 + cfg.tint * 0.04,
                 1.0 - abs(cfg.temperature) * 0.03 - cfg.tint * 0.16,
                 1.0 - cfg.temperature * 0.28 + cfg.tint * 0.04],
                device=x.device, dtype=x.dtype).view(1, 3, 1, 1)
            x = x * gain
        if cfg.contrast:
            c = 1.0 + cfg.contrast
            x = (x - 0.5) * c + 0.5
        if cfg.saturation:
            gray = ops.luminance(x)
            x = torch.lerp(gray.expand_as(x), x, 1.0 + cfg.saturation)
        if cfg.gamma:
            g = 2.0 ** (-cfg.gamma)          # gamma>0 => sáng vùng tối
            x = x.clamp(min=1e-5) ** g
        x = x.clamp(0, 1)
        if self._lut is not None and cfg.lut_strength > 0:
            x = apply_lut(x, self._lut, cfg.lut_strength)
        return x

    # ---------- làm đẹp ----------
    def apply_beauty(self, x: torch.Tensor, cfg: BeautyConfig,
                     subject: torch.Tensor | None = None) -> torch.Tensor:
        if cfg.smooth > 0.01:
            x = self._smooth_skin(x, cfg.smooth, cfg.skin_only, subject)
        if cfg.sharpen > 0.01:
            blur = ops.gaussian_blur(x, 1.2)
            x = (x + (x - blur) * (cfg.sharpen * 1.8)).clamp(0, 1)
        if cfg.vignette > 0.01:
            r = ops.radial_mask(x.shape[-2], x.shape[-1], str(x.device),
                                str(x.dtype).split(".")[-1])
            falloff = (1.0 - (r ** 2.2) * cfg.vignette).clamp(0, 1)
            x = x * falloff
        return x.clamp(0, 1)

    @staticmethod
    def _smooth_skin(x: torch.Tensor, amount: float, skin_only: bool,
                     subject: torch.Tensor | None) -> torch.Tensor:
        """'Surface blur' xấp xỉ: làm phẳng vùng đồng đều, giữ nguyên biên."""
        sigma = 1.5 + amount * 4.0
        blurred = ops.gaussian_blur(x, sigma)
        detail = x - blurred
        # nơi chi tiết mạnh (mắt, tóc, viền) thì giữ lại; nơi phẳng (da) thì bỏ
        edge = (detail.abs().mean(dim=1, keepdim=True) * 26.0).clamp(0, 1)
        keep = edge + (1.0 - amount) * (1.0 - edge)
        smoothed = blurred + detail * keep

        weight = torch.full_like(edge, float(amount))
        if skin_only:
            weight = weight * ops.skin_mask(x)
        if subject is not None:
            weight = weight * subject
        return torch.lerp(x, smoothed, weight.clamp(0, 1))

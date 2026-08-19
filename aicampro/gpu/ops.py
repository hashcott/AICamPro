"""Các toán tử ảnh dùng chung, chạy trên GPU bằng torch.

Quy ước tensor: (1, 3, H, W), float, giá trị 0..1, thứ tự kênh RGB.
"""
from __future__ import annotations

import math
from functools import lru_cache

import torch
import torch.nn.functional as F

LUMA = (0.299, 0.587, 0.114)


@lru_cache(maxsize=64)
def _gaussian_kernel(sigma: float, device: str, dtype_str: str) -> torch.Tensor:
    radius = max(1, int(math.ceil(sigma * 2.5)))
    xs = torch.arange(-radius, radius + 1, dtype=torch.float32)
    k = torch.exp(-(xs ** 2) / (2 * sigma * sigma))
    k = k / k.sum()
    return k.to(device=device, dtype=getattr(torch, dtype_str))


def gaussian_blur(x: torch.Tensor, sigma: float) -> torch.Tensor:
    """Gaussian tách rời (separable) — 2 lần conv1d theo trục."""
    if sigma <= 0.05:
        return x
    c = x.shape[1]
    k = _gaussian_kernel(round(float(sigma), 2), str(x.device), str(x.dtype).split(".")[-1])
    r = (k.numel() - 1) // 2
    kx = k.view(1, 1, 1, -1).expand(c, 1, 1, -1)
    ky = k.view(1, 1, -1, 1).expand(c, 1, -1, 1)
    x = F.conv2d(F.pad(x, (r, r, 0, 0), mode="reflect"), kx, groups=c)
    x = F.conv2d(F.pad(x, (0, 0, r, r), mode="reflect"), ky, groups=c)
    return x


def fast_blur(x: torch.Tensor, sigma: float, max_sigma_full: float = 3.0) -> torch.Tensor:
    """Blur mạnh: thu nhỏ -> blur -> phóng lại. Rẻ hơn nhiều mà nhìn như bokeh."""
    if sigma <= 0.05:
        return x
    if sigma <= max_sigma_full:
        return gaussian_blur(x, sigma)
    scale = min(8, max(2, int(sigma / max_sigma_full)))
    h, w = x.shape[-2:]
    sh, sw = max(8, h // scale), max(8, w // scale)
    small = F.interpolate(x, size=(sh, sw), mode="area")
    small = gaussian_blur(small, sigma / scale)
    return F.interpolate(small, size=(h, w), mode="bilinear", align_corners=False)


def luminance(x: torch.Tensor) -> torch.Tensor:
    w = torch.tensor(LUMA, device=x.device, dtype=x.dtype).view(1, 3, 1, 1)
    return (x * w).sum(dim=1, keepdim=True)


def dilate(a: torch.Tensor, radius: int) -> torch.Tensor:
    if radius <= 0:
        return a
    k = radius * 2 + 1
    return F.max_pool2d(a, k, stride=1, padding=radius)


def erode(a: torch.Tensor, radius: int) -> torch.Tensor:
    if radius <= 0:
        return a
    return 1.0 - dilate(1.0 - a, radius)


def pad_to_multiple(x: torch.Tensor, m: int = 8) -> tuple[torch.Tensor, tuple[int, int]]:
    h, w = x.shape[-2:]
    ph, pw = (-h) % m, (-w) % m
    if ph or pw:
        x = F.pad(x, (0, pw, 0, ph), mode="replicate")
    return x, (h, w)


def unpad(x: torch.Tensor, size: tuple[int, int]) -> torch.Tensor:
    h, w = size
    return x[..., :h, :w]


@lru_cache(maxsize=8)
def radial_mask(h: int, w: int, device: str, dtype_str: str) -> torch.Tensor:
    """Khoảng cách chuẩn hoá tới tâm (0 ở giữa, ~1 ở góc) — dùng cho vignette."""
    dtype = getattr(torch, dtype_str)
    ys = torch.linspace(-1, 1, h, device=device, dtype=dtype).view(1, 1, h, 1)
    xs = torch.linspace(-1, 1, w, device=device, dtype=dtype).view(1, 1, 1, w)
    return torch.sqrt(xs * xs + ys * ys) / math.sqrt(2.0)


def skin_mask(x: torch.Tensor) -> torch.Tensor:
    """Xác suất da đơn giản dựa trên tương quan kênh RGB — đủ tốt cho webcam."""
    r, g, b = x[:, 0:1], x[:, 1:2], x[:, 2:3]
    mx = torch.amax(x, dim=1, keepdim=True)
    mn = torch.amin(x, dim=1, keepdim=True)
    cond = (
        (r > 0.25).float()
        * (g > 0.16).float()
        * (b > 0.08).float()
        * ((mx - mn) > 0.05).float()
        * ((r - g) > 0.02).float()
        * ((r - b) > 0.04).float()
    )
    return gaussian_blur(cond, 3.0).clamp(0, 1)


def resize_cover(img: torch.Tensor, h: int, w: int, fit: str = "cover") -> torch.Tensor:
    """Đưa ảnh nền về đúng khung hình theo kiểu cover / contain / stretch."""
    if fit == "stretch":
        return F.interpolate(img, size=(h, w), mode="bilinear", align_corners=False)
    ih, iw = img.shape[-2:]
    scale = max(h / ih, w / iw) if fit == "cover" else min(h / ih, w / iw)
    nh, nw = max(1, int(round(ih * scale))), max(1, int(round(iw * scale)))
    out = F.interpolate(img, size=(nh, nw), mode="bilinear", align_corners=False)
    if fit == "cover":
        top, left = (nh - h) // 2, (nw - w) // 2
        return out[..., top:top + h, left:left + w]
    canvas = torch.zeros((1, img.shape[1], h, w), device=img.device, dtype=img.dtype)
    top, left = (h - nh) // 2, (w - nw) // 2
    canvas[..., top:top + nh, left:left + nw] = out
    return canvas

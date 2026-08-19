#!/usr/bin/env python3
"""Sinh bộ LUT (.cube) và ảnh nền mẫu cho AICamPro.

Chạy lại bất cứ lúc nào:  python scripts/make_assets.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
LUT_DIR = ROOT / "aicampro" / "assets" / "luts"
BG_DIR = ROOT / "aicampro" / "assets" / "backgrounds"
SIZE = 17


# ---------------------------------------------------------------- LUT
def _grid(size: int) -> np.ndarray:
    """Lưới RGB đầu vào theo thứ tự .cube (R chạy nhanh nhất)."""
    axis = np.linspace(0.0, 1.0, size)
    b, g, r = np.meshgrid(axis, axis, axis, indexing="ij")
    return np.stack([r, g, b], axis=-1).reshape(-1, 3)


def _luma(rgb: np.ndarray) -> np.ndarray:
    return (rgb * np.array([0.299, 0.587, 0.114])).sum(axis=-1, keepdims=True)


def _write_cube(name: str, rgb: np.ndarray, title: str) -> None:
    LUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f'TITLE "{title}"', f"LUT_3D_SIZE {SIZE}",
             "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0", ""]
    lines += [f"{r:.6f} {g:.6f} {b:.6f}" for r, g, b in np.clip(rgb, 0, 1)]
    (LUT_DIR / f"{name}.cube").write_text("\n".join(lines) + "\n")
    print(f"  ✓ {name}.cube")


def _contrast(x: np.ndarray, amount: float, pivot: float = 0.5) -> np.ndarray:
    return (x - pivot) * (1.0 + amount) + pivot


def build_luts() -> None:
    print("LUT →", LUT_DIR)
    base = _grid(SIZE)

    # 1. Warm Studio — da hồng hào, highlight ấm
    x = base.copy()
    x = _contrast(x, 0.10)
    x = x * np.array([1.06, 1.005, 0.94])
    x += np.array([0.012, 0.004, -0.006]) * (1.0 - _luma(base))
    _write_cube("01_warm_studio", x, "Warm Studio")

    # 2. Cool Cinema — bóng ngả teal, highlight ngả cam
    lum = _luma(base)
    shadow = np.clip(1.0 - lum * 2.0, 0, 1)
    highlight = np.clip(lum * 2.0 - 1.0, 0, 1)
    x = _contrast(base, 0.18)
    x += shadow * np.array([-0.045, 0.012, 0.075])
    x += highlight * np.array([0.055, 0.012, -0.05])
    _write_cube("02_cool_cinema", x, "Cool Cinema (teal & orange)")

    # 3. Soft Portrait — dịu, giảm tương phản, hơi hồng
    x = _contrast(base, -0.10)
    x = x * np.array([1.03, 0.995, 1.01]) + 0.018
    x = np.clip(x, 0, 1) ** np.array([0.97, 1.0, 1.02])
    _write_cube("03_soft_portrait", x, "Soft Portrait")

    # 4. Mono Contrast — đen trắng, tương phản cao
    g = _luma(base)
    g = _contrast(g, 0.35)
    _write_cube("04_mono_contrast", np.repeat(np.clip(g, 0, 1), 3, axis=-1), "Mono Contrast")

    # 5. Vintage Fade — đen nhấc lên, bạc màu
    x = base * 0.88 + 0.075
    x = x * 0.82 + _luma(base) * 0.18
    x += np.array([0.02, 0.0, 0.03])
    _write_cube("05_vintage_fade", x, "Vintage Fade")

    # 6. Punchy — nịnh mắt cho họp online
    x = _contrast(base, 0.22)
    x = _luma(x) + (x - _luma(x)) * 1.28
    x = x * np.array([1.02, 1.0, 0.99])
    _write_cube("06_punchy", x, "Punchy")


# ------------------------------------------------------- ảnh nền
def _save(name: str, img: np.ndarray) -> None:
    import cv2
    BG_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(BG_DIR / f"{name}.jpg"),
                np.clip(img, 0, 255).astype(np.uint8)[:, :, ::-1],
                [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"  ✓ {name}.jpg")


def build_backgrounds(w: int = 1920, h: int = 1080) -> None:
    import cv2
    print("Nền →", BG_DIR)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx, ny = xx / w, yy / h
    rng = np.random.default_rng(7)

    # 1. Studio tối với đèn hắt sau lưng
    d = np.sqrt((nx - 0.5) ** 2 + (ny - 0.42) ** 2 * 1.6)
    glow = np.exp(-(d ** 2) / 0.09)
    img = np.stack([26 + glow * 92, 28 + glow * 96, 34 + glow * 116], axis=-1)
    _save("01_studio_dark", img)

    # 2. Gradient hoàng hôn
    t = (nx * 0.35 + ny * 0.65)[..., None]
    img = np.array([242, 138, 74]) * (1 - t) + np.array([58, 44, 120]) * t
    _save("02_sunset_gradient", img)

    # 3. Văn phòng nhoè (đốm sáng bokeh)
    img = np.stack([np.full((h, w), 30.0), np.full((h, w), 36.0), np.full((h, w), 46.0)], -1)
    for _ in range(90):
        cx, cy = rng.integers(0, w), rng.integers(0, h)
        rad = int(rng.integers(24, 130))
        tone = rng.choice([(250, 214, 150), (150, 200, 250), (240, 240, 240)])
        overlay = np.zeros_like(img)
        cv2.circle(overlay, (int(cx), int(cy)), rad, tuple(float(c) for c in tone), -1)
        img += overlay * float(rng.uniform(0.10, 0.30))
    img = cv2.GaussianBlur(img, (0, 0), 22)
    _save("03_bokeh_office", img)

    # 4. Xanh lam nhạt phẳng, hợp cho họp hành
    t = ny[..., None]
    img = np.array([196, 214, 232]) * (1 - t) + np.array([132, 160, 194]) * t
    d = np.sqrt((nx - 0.5) ** 2 + (ny - 0.5) ** 2)[..., None]
    img *= (1.0 - 0.28 * (d / d.max()) ** 1.8)
    _save("04_soft_blue", img)


if __name__ == "__main__":
    build_luts()
    build_backgrounds()
    print("\nXong.")

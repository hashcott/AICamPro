"""Nạp và áp LUT màu định dạng .cube trên GPU (nội suy tam tuyến)."""
from __future__ import annotations

from pathlib import Path

import torch
import torch.nn.functional as F


class CubeLUT:
    def __init__(self, table: torch.Tensor, size: int, domain: tuple[float, float], name: str):
        # table: (1, 3, D, D, D) với trục (depth=B, height=G, width=R)
        self.table = table
        self.size = size
        self.domain = domain
        self.name = name

    def to(self, device, dtype=torch.float32) -> "CubeLUT":
        self.table = self.table.to(device=device, dtype=dtype)
        return self

    @classmethod
    def load(cls, path: str | Path) -> "CubeLUT":
        path = Path(path)
        size = 0
        dmin, dmax = 0.0, 1.0
        values: list[tuple[float, float, float]] = []
        for raw in path.read_text(errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            head, *rest = line.split()
            key = head.upper()
            if key == "LUT_3D_SIZE":
                size = int(rest[0])
            elif key == "DOMAIN_MIN":
                dmin = float(rest[0])
            elif key == "DOMAIN_MAX":
                dmax = float(rest[0])
            elif key in ("TITLE", "LUT_1D_SIZE", "LUT_3D_INPUT_RANGE"):
                continue
            else:
                try:
                    values.append((float(head), float(rest[0]), float(rest[1])))
                except (ValueError, IndexError):
                    continue
        if size == 0 or len(values) != size ** 3:
            raise ValueError(f"{path.name}: không phải LUT 3D hợp lệ (size={size}, dòng={len(values)})")

        # .cube: R biến thiên nhanh nhất -> reshape (B, G, R, 3)
        t = torch.tensor(values, dtype=torch.float32).view(size, size, size, 3)
        t = t.permute(3, 0, 1, 2).unsqueeze(0).contiguous()   # (1,3,B,G,R)
        return cls(t, size, (dmin, dmax), path.stem)


def apply_lut(x: torch.Tensor, lut: CubeLUT, strength: float = 1.0) -> torch.Tensor:
    """x: (1,3,H,W) RGB 0..1 -> ánh xạ qua LUT."""
    if strength <= 0.001:
        return x
    dmin, dmax = lut.domain
    span = max(1e-6, dmax - dmin)
    n = ((x - dmin) / span).clamp(0, 1)

    # grid_sample nhận toạ độ (x=W=R, y=H=G, z=D=B) trong [-1, 1]
    grid = torch.stack([n[:, 0], n[:, 1], n[:, 2]], dim=-1)      # (1,H,W,3)
    grid = grid.unsqueeze(1) * 2.0 - 1.0                          # (1,1,H,W,3)
    table = lut.table if lut.table.dtype == x.dtype else lut.table.to(x.dtype)
    out = F.grid_sample(table, grid, mode="bilinear",
                        padding_mode="border", align_corners=True)
    out = out.squeeze(2)                                          # (1,3,H,W)
    return torch.lerp(x, out.clamp(0, 1), float(strength))


def builtin_luts() -> dict[str, Path]:
    from ..config import ASSET_DIR
    d = ASSET_DIR / "luts"
    if not d.exists():
        return {}
    return {p.stem: p for p in sorted(d.glob("*.cube"))}

"""Phát hiện và mô tả thiết bị tính toán (ưu tiên GPU AMD qua ROCm)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DeviceInfo:
    torch_device: str          # "cuda" (ROCm ánh xạ vào namespace cuda) hoặc "cpu"
    name: str
    backend: str               # "ROCm" | "CUDA" | "CPU"
    total_mem_gb: float = 0.0
    supports_fp16: bool = False

    @property
    def is_gpu(self) -> bool:
        return self.torch_device != "cpu"

    def summary(self) -> str:
        if not self.is_gpu:
            return f"CPU · {self.name}"
        return f"{self.backend} · {self.name} · {self.total_mem_gb:.1f} GB"


_cached: DeviceInfo | None = None


def detect(prefer_index: int = 0) -> DeviceInfo:
    global _cached
    if _cached is not None:
        return _cached

    try:
        import torch
    except ImportError:
        _cached = DeviceInfo("cpu", "torch chưa được cài", "CPU")
        return _cached

    if torch.cuda.is_available():
        idx = min(prefer_index, torch.cuda.device_count() - 1)
        props = torch.cuda.get_device_properties(idx)
        backend = "ROCm" if getattr(torch.version, "hip", None) else "CUDA"
        _cached = DeviceInfo(
            torch_device=f"cuda:{idx}",
            name=props.name,
            backend=backend,
            total_mem_gb=props.total_memory / (1024 ** 3),
            supports_fp16=True,
        )
    else:
        import platform
        _cached = DeviceInfo("cpu", platform.processor() or "CPU", "CPU")
    return _cached


def gpu_memory_used_mb() -> float:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / (1024 ** 2)
    except Exception:
        pass
    return 0.0

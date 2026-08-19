"""Cấu hình AICamPro: dataclass lồng nhau + lưu/nạp JSON, hỗ trợ preset."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "aicampro"
CONFIG_FILE = CONFIG_DIR / "config.json"
PRESET_DIR = CONFIG_DIR / "presets"
REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO_ROOT / "models"
ASSET_DIR = REPO_ROOT / "assets"


@dataclass
class CaptureConfig:
    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30
    fourcc: str = "MJPG"          # MJPG cho fps cao, YUYV nếu camera không hỗ trợ
    mirror: bool = True           # lật ngang như gương


@dataclass
class SegmentationConfig:
    enabled: bool = True
    model: str = "rvm_mobilenetv3_fp32"   # tên file .torchscript trong models/
    downsample: float = 0.0       # 0 = tự động theo độ phân giải
    feather: float = 0.0          # làm mềm biên alpha (px sigma)
    shift: float = 0.0            # -1..1 : co (âm) / nở (dương) vùng người
    contrast: float = 0.0         # 0..1 : tăng độ dứt khoát của alpha


@dataclass
class BackgroundConfig:
    mode: str = "blur"            # none | blur | image | color | greenscreen | transparent
    blur: float = 0.6             # 0..1
    image_path: str = ""
    color: tuple = (18, 18, 22)   # RGB
    green: tuple = (0, 177, 64)
    image_fit: str = "cover"      # cover | contain | stretch


@dataclass
class FilterConfig:
    exposure: float = 0.0         # -1..1
    contrast: float = 0.0         # -1..1
    saturation: float = 0.0       # -1..1
    temperature: float = 0.0      # -1..1 (lạnh -> ấm)
    tint: float = 0.0             # -1..1 (xanh lá -> hồng)
    gamma: float = 0.0            # -1..1
    lut_path: str = ""
    lut_strength: float = 1.0     # 0..1


@dataclass
class BeautyConfig:
    smooth: float = 0.0           # 0..1 làm mịn da
    skin_only: bool = True        # chỉ áp lên vùng da
    sharpen: float = 0.0          # 0..1
    vignette: float = 0.0         # 0..1


@dataclass
class AutoFrameConfig:
    enabled: bool = False
    source: str = "auto"          # auto | mask | face
    zoom: float = 1.15            # hệ số phóng quanh chủ thể
    smoothing: float = 0.88       # 0..0.99, càng cao càng mượt/chậm
    max_zoom: float = 1.8         # phóng quá tay là mất nét, xem ghi chú ở README


@dataclass
class OutputConfig:
    width: int = 0                # 0 = giữ nguyên độ phân giải nguồn
    height: int = 0
    vcam_enabled: bool = False
    vcam_device: str = ""         # "" = tự chọn thiết bị v4l2loopback đầu tiên
    record_dir: str = str(Path.home() / "Videos" / "AICamPro")
    encoder: str = "auto"         # auto | vaapi | x264
    record_fps: int = 30


@dataclass
class AppConfig:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    beauty: BeautyConfig = field(default_factory=BeautyConfig)
    autoframe: AutoFrameConfig = field(default_factory=AutoFrameConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    # ---------- serialize ----------
    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path | None = None) -> Path:
        path = Path(path) if path else CONFIG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        path = Path(path) if path else CONFIG_FILE
        cfg = cls()
        if path.exists():
            try:
                _merge(cfg, json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        return cfg

    def apply_dict(self, data: dict) -> None:
        _merge(self, data)


def _merge(obj: Any, data: dict) -> None:
    """Gán đệ quy dict vào dataclass, bỏ qua khóa lạ và kiểu sai."""
    if not is_dataclass(obj) or not isinstance(data, dict):
        return
    known = {f.name: f for f in fields(obj)}
    for key, value in data.items():
        f = known.get(key)
        if f is None:
            continue
        current = getattr(obj, key)
        if is_dataclass(current):
            _merge(current, value)
        elif isinstance(current, tuple) and isinstance(value, (list, tuple)):
            setattr(obj, key, tuple(value))
        elif value is None:
            continue
        else:
            try:
                setattr(obj, key, type(current)(value))
            except (TypeError, ValueError):
                pass


def resolve_asset(path: str) -> Path | None:
    """Đường dẫn tương đối trong config được hiểu là tương đối với gốc dự án."""
    if not path:
        return None
    p = Path(path).expanduser()
    if p.is_absolute():
        return p if p.exists() else None
    for base in (Path.cwd(), REPO_ROOT):
        candidate = (base / p).resolve()
        if candidate.exists():
            return candidate
    return None


# ---------- preset ----------
def list_presets() -> list[str]:
    if not PRESET_DIR.exists():
        return []
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def save_preset(name: str, cfg: AppConfig) -> Path:
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path = PRESET_DIR / f"{name}.json"
    # preset không lưu thiết bị/đường dẫn ghi hình
    data = cfg.to_dict()
    data.pop("output", None)
    data.get("capture", {}).pop("device", None)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return path


def load_preset(name: str, cfg: AppConfig) -> None:
    path = PRESET_DIR / f"{name}.json"
    if path.exists():
        cfg.apply_dict(json.loads(path.read_text()))


def delete_preset(name: str) -> None:
    (PRESET_DIR / f"{name}.json").unlink(missing_ok=True)

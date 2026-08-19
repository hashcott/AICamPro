"""Ghi video (ffmpeg, ưu tiên encoder phần cứng) và chụp ảnh tĩnh."""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np


def _amd_render_node() -> str | None:
    """Tìm /dev/dri/renderD* thuộc card AMD (vendor 0x1002) để mã hoá VAAPI."""
    for node in sorted(Path("/sys/class/drm").glob("renderD*")):
        try:
            vendor = (node / "device" / "vendor").read_text().strip()
        except OSError:
            continue
        if vendor == "0x1002":
            path = Path("/dev/dri") / node.name
            if path.exists():
                return str(path)
    return None


def _unique(path: Path) -> Path:
    """Thêm hậu tố _2, _3… nếu tên file đã tồn tại (mốc thời gian chỉ tới giây)."""
    if not path.exists():
        return path
    for n in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path


def available_encoders() -> list[str]:
    out = ["x264"]
    if shutil.which("ffmpeg") and _amd_render_node():
        try:
            enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                 capture_output=True, text=True, timeout=5).stdout
            if "h264_vaapi" in enc:
                out.insert(0, "vaapi")
        except (OSError, subprocess.SubprocessError):
            pass
    return out


class Recorder:
    """Nhận khung BGR uint8, đẩy qua stdin của ffmpeg."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self.path: Path | None = None
        self.frames = 0
        self.error: str | None = None
        self.size: tuple[int, int] = (0, 0)      # (rộng, cao) đã khai báo với ffmpeg

    @property
    def is_recording(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, out_dir: str, width: int, height: int, fps: int,
              encoder: str = "auto") -> Path:
        if self.is_recording:
            return self.path                                    # type: ignore[return-value]
        if not shutil.which("ffmpeg"):
            raise RuntimeError("Không tìm thấy ffmpeg (sudo apt install ffmpeg)")

        directory = Path(out_dir).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        path = _unique(directory / f"procam_{datetime.now():%Y%m%d_%H%M%S}.mp4")

        if encoder == "auto":
            encoder = available_encoders()[0]
        render_node = _amd_render_node()
        if encoder == "vaapi" and not render_node:
            encoder = "x264"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}", "-r", str(max(1, fps)),
            "-i", "pipe:0",
        ]
        if encoder == "vaapi":
            cmd += [
                "-vaapi_device", render_node,
                "-vf", "format=nv12,hwupload",
                "-c:v", "h264_vaapi", "-qp", "22",
            ]
        else:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p"]
        cmd += ["-movflags", "+faststart", str(path)]

        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE)
        self.path = path
        self.frames = 0
        self.error = None
        self.size = (width, height)
        return path

    def write(self, bgr: np.ndarray) -> None:
        if not self.is_recording or self._proc is None or self._proc.stdin is None:
            return
        h, w = bgr.shape[:2]
        if (w, h) != self.size:
            # đổi độ phân giải giữa chừng sẽ làm hỏng file — dừng lại thay vì ghi rác
            self.error = (f"Độ phân giải đổi từ {self.size[0]}×{self.size[1]} "
                          f"sang {w}×{h} khi đang ghi — đã dừng ghi hình")
            self.stop()
            return
        try:
            self._proc.stdin.write(np.ascontiguousarray(bgr).tobytes())
            self.frames += 1
        except (BrokenPipeError, OSError) as exc:
            self.error = f"ffmpeg dừng đột ngột: {exc}"
            self.stop()

    def stop(self) -> Path | None:
        proc, self._proc = self._proc, None
        if proc is None:
            return self.path
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, OSError):
            proc.kill()
        if proc.returncode not in (0, None) and not self.error:
            err = proc.stderr.read().decode(errors="replace")[-400:] if proc.stderr else ""
            self.error = err or f"ffmpeg thoát với mã {proc.returncode}"
        return self.path


def snapshot(bgr: np.ndarray, out_dir: str, alpha: np.ndarray | None = None) -> Path:
    """Lưu ảnh; nếu có alpha thì xuất PNG nền trong suốt."""
    directory = Path(out_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S_%f}"[:-3]
    if alpha is not None:
        path = _unique(directory / f"procam_{stamp}.png")
        cv2.imwrite(str(path), np.dstack([bgr, alpha]))
    else:
        path = _unique(directory / f"procam_{stamp}.jpg")
        cv2.imwrite(str(path), bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return path

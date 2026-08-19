"""Luồng đọc camera V4L2 — luôn giữ khung mới nhất, không bao giờ chặn pipeline."""
from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from ..config import CaptureConfig
from . import v4l2


class CameraCapture:
    def __init__(self, cfg: CaptureConfig):
        self.cfg = cfg
        self._cap: cv2.VideoCapture | None = None
        self._frame: np.ndarray | None = None
        self._seq = 0
        self._lock = threading.Lock()
        self._new = threading.Condition(self._lock)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.error: str | None = None
        self.actual: tuple[int, int, float] = (0, 0, 0.0)
        self._fps_ts: list[float] = []

    # ---------- vòng đời ----------
    def open(self) -> None:
        cap = cv2.VideoCapture(self.cfg.device, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"Không mở được camera {self.cfg.device}")
        if self.cfg.fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.cfg.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        # BUFFERSIZE=1 làm driver V4L2 tụt còn ~nửa fps; 2 vẫn giữ độ trễ 1 khung
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        self._cap = cap
        self.actual = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                       int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                       float(cap.get(cv2.CAP_PROP_FPS)))

    def start(self) -> None:
        if self._thread is not None:
            return
        self.open()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="soi-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with self._lock:
            self._frame = None

    def restart(self, cfg: CaptureConfig) -> None:
        self.stop()
        self.cfg = cfg
        self.start()

    # ---------- luồng đọc ----------
    def _loop(self) -> None:
        misses = 0
        while not self._stop.is_set():
            cap = self._cap
            if cap is None:
                break
            ok, frame = cap.read()
            if not ok or frame is None:
                misses += 1
                if misses > 60:
                    self.error = "Mất tín hiệu camera"
                    break
                time.sleep(0.01)
                continue
            misses = 0
            if self.cfg.mirror:
                frame = cv2.flip(frame, 1)
            now = time.perf_counter()
            with self._new:
                self._frame = frame
                self._seq += 1
                self._fps_ts.append(now)
                if len(self._fps_ts) > 30:
                    self._fps_ts.pop(0)
                self._new.notify_all()

    # ---------- đọc ----------
    def latest(self, last_seq: int = -1, timeout: float = 0.5):
        """Chờ khung mới hơn last_seq. Trả về (frame BGR, seq) hoặc (None, last_seq)."""
        with self._new:
            if self._seq <= last_seq:
                self._new.wait(timeout)
            if self._frame is None or self._seq <= last_seq:
                return None, last_seq
            return self._frame, self._seq

    @property
    def fps(self) -> float:
        with self._lock:
            ts = list(self._fps_ts)
        if len(ts) < 2:
            return 0.0
        span = ts[-1] - ts[0]
        return (len(ts) - 1) / span if span > 0 else 0.0


def list_cameras() -> list[v4l2.V4L2Device]:
    return v4l2.capture_devices()

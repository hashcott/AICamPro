"""Luồng xử lý chính: camera → GPU (tách nền, ghép, filter, bám khung) → đầu ra."""
from __future__ import annotations

import queue
import time
import traceback
from dataclasses import dataclass

import numpy as np
import torch
from PySide6.QtCore import QThread, Signal

from ..config import AppConfig
from ..gpu import device as gpu_device
from ..gpu import segmentation as seg
from ..gpu.compose import BackgroundCompositor
from ..gpu.filters import FilterStack
from ..vision.autoframe import AutoFramer
from .capture import CameraCapture
from .recorder import Recorder, snapshot
from .vcam import VirtualCamera, VirtualCameraError


@dataclass
class Stats:
    capture_fps: float = 0.0
    process_fps: float = 0.0
    gpu_ms: float = 0.0
    vram_mb: float = 0.0
    resolution: str = "—"
    vcam: str = ""
    recording: bool = False
    rec_seconds: float = 0.0
    device: str = ""


@dataclass
class Frame:
    """Kết quả một khung hình, dùng cho preview và đầu ra."""
    rgb: np.ndarray
    alpha: np.ndarray | None = None


class Pipeline(QThread):
    frameReady = Signal(object)        # Frame
    statsReady = Signal(object)        # Stats
    status = Signal(str, int)          # thông điệp, mức (0=info, 1=cảnh báo, 2=lỗi)
    cameraListChanged = Signal()

    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.info = gpu_device.detect()
        self._commands: queue.Queue = queue.Queue()
        self._running = False

        self.capture = CameraCapture(cfg.capture)
        self.matter: seg.Matter = seg.NullMatter()
        self.compositor: BackgroundCompositor | None = None
        self.filters: FilterStack | None = None
        self.framer = AutoFramer()
        self.vcam = VirtualCamera()
        self.recorder = Recorder()

        self._matter_name = ""
        self._proc_ts: list[float] = []
        self._rec_start = 0.0
        self._last_error = ""
        self._pending_snapshot = False
        self._gpu_ms = 0.0
        self._warned_missing_bg = False

    # ================= API gọi từ luồng giao diện =================
    def post(self, name: str, **kwargs) -> None:
        self._commands.put((name, kwargs))

    def stop(self) -> None:
        self._running = False
        self.wait(3000)

    # ================= vòng đời luồng =================
    def run(self) -> None:
        self._running = True
        dev = self.info.torch_device
        self.compositor = BackgroundCompositor(dev)
        self.filters = FilterStack(dev)

        try:
            self.capture.start()
        except RuntimeError as exc:
            self.status.emit(str(exc), 2)
            return

        self._ensure_matter()
        self.status.emit(f"Sẵn sàng · {self.info.summary()}", 0)

        last_seq = -1
        last_stats = 0.0
        while self._running:
            self._drain_commands()

            frame, last_seq = self.capture.latest(last_seq, timeout=0.3)
            if frame is None:
                if self.capture.error:
                    self.status.emit(self.capture.error, 2)
                    self.capture.error = None
                continue

            t0 = time.perf_counter()
            try:
                result = self._process(frame)
            except Exception:                                  # pylint: disable=broad-except
                msg = traceback.format_exc(limit=3)
                if msg != self._last_error:
                    self._last_error = msg
                    self.status.emit(f"Lỗi xử lý khung hình:\n{msg}", 2)
                result = Frame(np.ascontiguousarray(frame[:, :, ::-1]))
            elapsed = (time.perf_counter() - t0) * 1000.0

            self._dispatch(result)
            self._track_fps(elapsed)

            now = time.perf_counter()
            if now - last_stats > 0.4:
                last_stats = now
                self.statsReady.emit(self._stats(result))

        self._teardown()

    def _teardown(self) -> None:
        if self.recorder.is_recording:
            self.recorder.stop()
        self.vcam.close()
        self.capture.stop()
        self.matter.close()

    # ================= lệnh =================
    def _drain_commands(self) -> None:
        while True:
            try:
                name, kwargs = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle(name, kwargs)
            except Exception as exc:                           # pylint: disable=broad-except
                self.status.emit(f"{name}: {exc}", 2)

    def _handle(self, name: str, kwargs: dict) -> None:
        if name == "restart_capture":
            self.capture.restart(self.cfg.capture)
            self.matter.reset()
            self.framer.reset()
            self.vcam.close()
            w, h, fps = self.capture.actual
            self.status.emit(f"Camera: {self.cfg.capture.device} · {w}×{h} @ {fps:.0f}fps", 0)
        elif name == "reload_model":
            self._matter_name = ""
            self._ensure_matter()
        elif name == "reset_state":
            self.matter.reset()
            self.framer.reset()
        elif name == "vcam":
            if not self.cfg.output.vcam_enabled:
                self.vcam.close()
                self.status.emit("Đã tắt webcam ảo", 0)
            else:
                self.vcam.close()          # mở lại ở khung kế tiếp
        elif name == "record_start":
            w, h = kwargs.get("size", (0, 0))
            if w and h:
                path = self.recorder.start(self.cfg.output.record_dir, w, h,
                                           self.cfg.output.record_fps,
                                           self.cfg.output.encoder)
                self._rec_start = time.perf_counter()
                self.status.emit(f"Đang ghi: {path}", 0)
        elif name == "record_stop":
            path = self.recorder.stop()
            if self.recorder.error:
                self.status.emit(self.recorder.error, 2)
            elif path:
                self.status.emit(f"Đã lưu video: {path} ({self.recorder.frames} khung)", 0)
        elif name == "snapshot":
            self._pending_snapshot = True

    def _ensure_matter(self) -> None:
        want = self.cfg.segmentation.model
        if self._matter_name == want and not isinstance(self.matter, seg.NullMatter):
            return
        try:
            self.matter = seg.create_matter(want, self.info.torch_device,
                                            self.cfg.segmentation.downsample)
            self._matter_name = want
            self.status.emit(f"Model tách nền: {want}", 0)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            self.matter = seg.NullMatter()
            self._matter_name = ""
            self.status.emit(str(exc), 2)

    def _sync_background(self, bg) -> None:
        """Nạp ảnh nền theo cấu hình hiện tại (tự bỏ qua nếu đường dẫn không đổi)."""
        assert self.compositor is not None
        if bg.mode != "image":
            self._warned_missing_bg = False
            return
        err = self.compositor.set_image(bg.image_path)
        if err:
            self.status.emit(f"Ảnh nền: {err}", 1)
            bg.image_path = ""
            self._warned_missing_bg = True
        elif not bg.image_path:
            if not self._warned_missing_bg:
                self._warned_missing_bg = True
                self.status.emit("Đang ở chế độ «Thay bằng ảnh» nhưng chưa chọn ảnh — "
                                 "tạm dùng màu đặc. Bấm «Chọn ảnh nền…».", 1)
        else:
            self._warned_missing_bg = False

    def _output_size(self, h: int, w: int) -> tuple[int, int]:
        """Kích thước xuất ra; 0 nghĩa là giữ nguyên độ phân giải nguồn."""
        ow, oh = self.cfg.output.width, self.cfg.output.height
        if ow <= 0 or oh <= 0:
            return h, w
        return int(oh), int(ow)

    # ================= xử lý một khung =================
    @torch.inference_mode()
    def _process(self, bgr: np.ndarray) -> Frame:
        cfg = self.cfg
        dev = self.info.torch_device
        assert self.compositor is not None and self.filters is not None

        t = torch.from_numpy(np.ascontiguousarray(bgr)).to(dev, non_blocking=True)
        rgb = t[:, :, [2, 1, 0]].permute(2, 0, 1).unsqueeze(0).float().div_(255.0)

        alpha = fgr = None
        need_mask = cfg.segmentation.enabled and (
            cfg.background.mode != "none"
            or (cfg.autoframe.enabled and cfg.autoframe.source in ("auto", "mask"))
        )
        if need_mask:
            if isinstance(self.matter, seg.NullMatter):
                self._ensure_matter()
            # dùng giao diện Matter, không kiểm tra lớp cụ thể — nếu không mọi
            # backend tách nền khác sẽ lặng lẽ bị bỏ qua
            if not isinstance(self.matter, seg.NullMatter):
                self.matter.configure(downsample=cfg.segmentation.downsample)
                alpha, fgr = self.matter.alpha(rgb)
                alpha = seg.refine_alpha(alpha, cfg.segmentation.feather,
                                         cfg.segmentation.shift,
                                         cfg.segmentation.contrast)

        self._sync_background(cfg.background)
        composed = self.compositor.compose(rgb, alpha, fgr, cfg.background)
        # framer cắt cả ảnh lẫn alpha (luôn theo tỉ lệ đầu ra) rồi đưa về đúng kích thước
        out_size = self._output_size(*rgb.shape[-2:])
        out, alpha = self.framer.apply(composed, cfg.autoframe, alpha, bgr, out_size)

        err = self.filters.set_lut(cfg.filters.lut_path)
        if err:
            self.status.emit(f"LUT: {err}", 1)
            cfg.filters.lut_path = ""
        out = self.filters.apply_color(out, cfg.filters)
        out = self.filters.apply_beauty(out, cfg.beauty, subject=alpha)

        u8 = (out.clamp(0, 1) * 255).round_().to(torch.uint8)
        u8 = u8.squeeze(0).permute(1, 2, 0).contiguous()
        rgb_np = u8.cpu().numpy()

        alpha_np = None
        if cfg.background.mode == "transparent" and alpha is not None:
            a = (alpha.clamp(0, 1) * 255).round_().to(torch.uint8)
            alpha_np = a.squeeze(0).squeeze(0).contiguous().cpu().numpy()
        return Frame(rgb_np, alpha_np)

    # ================= phân phối đầu ra =================
    def _dispatch(self, frame: Frame) -> None:
        cfg = self.cfg
        h, w = frame.rgb.shape[:2]

        if cfg.output.vcam_enabled:
            try:
                self.vcam.send(frame.rgb, cfg.capture.fps, cfg.output.vcam_device)
            except VirtualCameraError as exc:
                cfg.output.vcam_enabled = False
                self.status.emit(str(exc), 2)

        if self.recorder.is_recording or self._pending_snapshot:
            bgr = np.ascontiguousarray(frame.rgb[:, :, ::-1])
            if self.recorder.is_recording:
                self.recorder.write(bgr)
                if self.recorder.error:
                    self.status.emit(self.recorder.error, 1)
                    self.recorder.error = None
            if self._pending_snapshot:
                self._pending_snapshot = False
                path = snapshot(bgr, cfg.output.record_dir, frame.alpha)
                self.status.emit(f"Đã chụp: {path}", 0)

        self.frameReady.emit(frame)

    # ================= thống kê =================
    def _track_fps(self, elapsed_ms: float) -> None:
        now = time.perf_counter()
        self._proc_ts.append(now)
        if len(self._proc_ts) > 40:
            self._proc_ts.pop(0)
        self._gpu_ms = elapsed_ms

    def _stats(self, frame: Frame) -> Stats:
        span = self._proc_ts[-1] - self._proc_ts[0] if len(self._proc_ts) > 1 else 0.0
        pfps = (len(self._proc_ts) - 1) / span if span > 0 else 0.0
        h, w = frame.rgb.shape[:2]
        return Stats(
            capture_fps=self.capture.fps,
            process_fps=pfps,
            gpu_ms=self._gpu_ms,
            vram_mb=gpu_device.gpu_memory_used_mb(),
            resolution=f"{w}×{h}",
            vcam=self.vcam.device if self.vcam.is_open else "",
            recording=self.recorder.is_recording,
            rec_seconds=(time.perf_counter() - self._rec_start) if self.recorder.is_recording else 0.0,
            device=self.info.summary(),
        )

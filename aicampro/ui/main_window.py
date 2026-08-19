"""Cửa sổ chính AICamPro."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QLabel,
                               QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .. import config as cfgmod
from ..config import ASSET_DIR, AppConfig
from ..core.camera_controls import (EXPOSURE_APERTURE_PRIORITY,
                                    EXPOSURE_MANUAL, CameraControls)
from ..core.capture import list_cameras
from ..core.pipeline import Frame, Pipeline, Stats
from ..core.recorder import available_encoders
from ..core.vcam import VirtualCamera
from ..gpu import segmentation as seg
from ..gpu.lut import builtin_luts
from . import style
from .preview import PreviewWidget
from .widgets import (ColorButton, LabeledCombo, Section, SliderRow, ToggleRow,
                      separator)

BG_MODES = [
    ("none", "Giữ nguyên nền"),
    ("blur", "Làm mờ nền"),
    ("image", "Thay bằng ảnh"),
    ("color", "Màu đặc"),
    ("greenscreen", "Phông xanh ảo"),
    ("transparent", "Nền trong suốt"),
]
FIT_MODES = [("cover", "Lấp đầy"), ("contain", "Vừa khung"), ("stretch", "Kéo giãn")]
FRAME_SOURCES = [("auto", "Tự động"), ("mask", "Theo chủ thể"), ("face", "Theo khuôn mặt")]


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = cfg
        self._loading = False
        self._last_frame: Frame | None = None

        # Qt tự nối applicationDisplayName ("AICamPro") vào sau, nên không lặp tên ở đây
        self.setWindowTitle("Webcam AI tăng tốc bằng GPU AMD")
        self.resize(1440, 860)

        self.pipeline = Pipeline(cfg)
        self._cam_controls: CameraControls | None = None
        self._ctrl_widgets: dict[str, QWidget] = {}
        self._build_ui()
        self._load_from_config()
        self._connect_pipeline()
        self._register_shortcuts()
        self.pipeline.start()

    # ================================================================
    # dựng giao diện
    # ================================================================
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 12, 14, 0)
        outer.setSpacing(10)

        outer.addLayout(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addLayout(self._build_left(), 1)
        body.addWidget(self._build_panel(), 0)
        outer.addLayout(body, 1)

        outer.addWidget(self._build_statusbar())

    # ---------- header ----------
    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        title = QLabel("AICamPro")
        title.setObjectName("Title")
        row.addWidget(title)

        self.device_chip = QLabel(self.pipeline.info.summary())
        self.device_chip.setObjectName("Chip")
        row.addWidget(self.device_chip)
        row.addStretch(1)

        self.preset_combo = LabeledCombo("Preset")
        self.preset_combo.setFixedWidth(260)
        self.preset_combo.changed.connect(self._on_preset_selected)
        row.addWidget(self.preset_combo)

        save = QPushButton("Lưu preset")
        save.clicked.connect(self._save_preset)
        row.addWidget(save)

        delete = QPushButton("Xoá")
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete_preset)
        row.addWidget(delete)

        reset = QPushButton("Đặt lại tất cả")
        reset.clicked.connect(self._reset_all)
        row.addWidget(reset)
        return row

    # ---------- cột trái: preview + nút hành động ----------
    def _build_left(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(10)

        self.preview = PreviewWidget()
        col.addWidget(self.preview, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_vcam = QPushButton("Bật webcam ảo")
        self.btn_vcam.setCheckable(True)
        self.btn_vcam.setObjectName("Accent")
        self.btn_vcam.setMinimumHeight(34)
        self.btn_vcam.toggled.connect(self._on_vcam_toggled)
        bar.addWidget(self.btn_vcam)

        self.btn_record = QPushButton("⏺  Ghi hình")
        self.btn_record.setCheckable(True)
        self.btn_record.setMinimumHeight(34)
        self.btn_record.toggled.connect(self._on_record_toggled)
        bar.addWidget(self.btn_record)

        self.btn_snap = QPushButton("📷  Chụp ảnh")
        self.btn_snap.setMinimumHeight(34)
        self.btn_snap.clicked.connect(lambda: self.pipeline.post("snapshot"))
        bar.addWidget(self.btn_snap)

        bar.addStretch(1)

        self.btn_open_dir = QPushButton("Mở thư mục lưu")
        self.btn_open_dir.clicked.connect(self._open_record_dir)
        bar.addWidget(self.btn_open_dir)

        col.addLayout(bar)
        return col

    # ---------- cột phải: bảng điều khiển ----------
    def _build_panel(self) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 0, 8, 8)
        lay.setSpacing(8)

        lay.addWidget(self._section_source())
        lay.addWidget(self._section_camera())
        lay.addWidget(self._section_background())
        lay.addWidget(self._section_color())
        lay.addWidget(self._section_beauty())
        lay.addWidget(self._section_frame())
        lay.addWidget(self._section_output())
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(388)
        scroll.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._panel_scroll = scroll
        return scroll

    # ================================================================
    # các nhóm thiết lập
    # ================================================================
    def _section_source(self) -> Section:
        s = Section("Nguồn video")
        self.cam_combo = LabeledCombo("Camera")
        self.cam_combo.bind(self._on_camera_changed)
        s.add(self.cam_combo)

        self.res_combo = LabeledCombo("Độ phân giải")
        self.res_combo.bind(self._on_resolution_changed)
        s.add(self.res_combo)

        self.fps_combo = LabeledCombo("Tốc độ khung")
        self.fps_combo.bind(self._on_fps_changed)
        s.add(self.fps_combo)

        self.fmt_combo = LabeledCombo("Định dạng")
        self.fmt_combo.bind(self._on_format_changed)
        s.add(self.fmt_combo)

        self.mirror_toggle = ToggleRow("Lật gương", True)
        self.mirror_toggle.bind(lambda v: setattr(self.cfg.capture, "mirror", v))
        s.add(self.mirror_toggle)

        refresh = QPushButton("Quét lại thiết bị")
        refresh.clicked.connect(lambda: self._refresh_devices(True))
        s.add(refresh)
        return s

    def _section_camera(self) -> Section:
        """Control phần cứng của camera — dựng lại mỗi khi đổi thiết bị."""
        s = Section("Camera (phần cứng)", expanded=False)
        s.add_hint("Các giá trị này do camera lưu và giữ nguyên sau khi thoát AICamPro. "
                   "Hình quá tối hoặc cháy sáng thì bật lại «Phơi sáng tự động».")
        self._camera_box = QWidget()
        self._camera_form = QVBoxLayout(self._camera_box)
        self._camera_form.setContentsMargins(0, 0, 0, 0)
        self._camera_form.setSpacing(9)
        s.add(self._camera_box)

        reset = QPushButton("Đặt lại mặc định camera")
        reset.clicked.connect(self._reset_camera_controls)
        s.add(reset)
        self._camera_section = s
        return s

    def _rebuild_camera_controls(self) -> None:
        while self._camera_form.count():
            item = self._camera_form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._ctrl_widgets.clear()

        if self._cam_controls is not None:
            self._cam_controls.close()
        self._cam_controls = CameraControls(self.cfg.capture.device)
        controls = self._cam_controls.available()
        if not controls:
            label = QLabel("Camera không cho chỉnh thông số qua V4L2.")
            label.setObjectName("Hint")
            self._camera_form.addWidget(label)
            return

        manual_exposure = False
        for c in controls:
            if c.key == "exposure_auto":
                # menu UVC: 1 = thủ công, 3 = ưu tiên khẩu độ (tự động)
                manual_exposure = c.value == EXPOSURE_MANUAL
                row = ToggleRow(c.label, not manual_exposure)
                row.bind(lambda on, cid=c.id: self._set_camera_control(
                    cid, EXPOSURE_APERTURE_PRIORITY if on else EXPOSURE_MANUAL,
                    "exposure_auto"))
            elif c.is_bool:
                row = ToggleRow(c.label, bool(c.value))
                row.bind(lambda on, cid=c.id, k=c.key: self._set_camera_control(
                    cid, int(on), k))
            else:
                row = SliderRow(c.label, c.minimum, c.maximum, c.value, integer=True)
                row.bind(lambda v, cid=c.id, k=c.key: self._set_camera_control(
                    cid, int(v), k))
            self._ctrl_widgets[c.key] = row
            self._camera_form.addWidget(row)

        self._update_camera_visibility()
        if manual_exposure:
            self._camera_section.header.setChecked(True)
            # hoãn lại để không bị các thông báo khởi động của pipeline ghi đè
            QTimer.singleShot(3000, lambda: self._set_status(
                "Camera đang ở chế độ phơi sáng thủ công — nếu hình tối, "
                "bật «Phơi sáng tự động» trong mục Camera (phần cứng).", 1))

    def _set_camera_control(self, cid: int, value: int, key: str) -> None:
        if self._cam_controls is None:
            return
        if not self._cam_controls.set(cid, value):
            self._set_status(f"Camera từ chối đổi «{key}» (có thể đang bị chế độ tự động khoá)", 1)
        if key in ("exposure_auto", "auto_white_balance"):
            self._update_camera_visibility()

    def _update_camera_visibility(self) -> None:
        """Ẩn control thủ công khi chế độ tự động tương ứng đang bật."""
        auto_exp = self._ctrl_widgets.get("exposure_auto")
        for key in ("exposure_absolute", "exposure_auto_priority"):
            widget = self._ctrl_widgets.get(key)
            if widget is not None and isinstance(auto_exp, ToggleRow):
                widget.setVisible(not auto_exp.is_checked())
        auto_wb = self._ctrl_widgets.get("auto_white_balance")
        wb = self._ctrl_widgets.get("white_balance_temperature")
        if wb is not None and isinstance(auto_wb, ToggleRow):
            wb.setVisible(not auto_wb.is_checked())

    def _reset_camera_controls(self) -> None:
        if self._cam_controls is None:
            return
        changed = self._cam_controls.reset_defaults()
        self._rebuild_camera_controls()
        self._set_status(f"Đã đặt lại {changed} thông số camera về mặc định", 0)

    def _section_background(self) -> Section:
        s = Section("Nền")
        self.seg_toggle = ToggleRow("Bật tách nền AI", True)
        self.seg_toggle.bind(self._on_seg_toggled)
        s.add(self.seg_toggle)

        self.model_combo = LabeledCombo("Model")
        self.model_combo.bind(self._on_model_changed)
        s.add(self.model_combo)

        self.bgmode_combo = LabeledCombo("Chế độ")
        self.bgmode_combo.bind(self._on_bgmode_changed)
        s.add(self.bgmode_combo)

        self.blur_slider = SliderRow("Độ mờ", 0.0, 1.0, 0.6)
        self.blur_slider.bind(lambda v: setattr(self.cfg.background, "blur", v))
        s.add(self.blur_slider)

        self.bg_image_btn = QPushButton("Chọn ảnh nền…")
        self.bg_image_btn.clicked.connect(self._pick_background_image)
        self.bg_clear_btn = QPushButton("Bỏ ảnh")
        self.bg_clear_btn.clicked.connect(lambda: self._set_background_image(""))
        self.bg_row = s.add_row(self.bg_image_btn, self.bg_clear_btn)

        self.bg_image_label = QLabel("—")
        self.bg_image_label.setObjectName("Hint")
        self.bg_image_label.setWordWrap(True)
        s.add(self.bg_image_label)

        self.fit_combo = LabeledCombo("Căn ảnh")
        self.fit_combo.bind(lambda v: setattr(self.cfg.background, "image_fit", v))
        s.add(self.fit_combo)

        self.color_label = QLabel("Màu nền")
        self.color_label.setObjectName("RowLabel")
        self.color_btn = ColorButton(self.cfg.background.color)
        self.color_btn.colorChanged.connect(
            lambda rgb: setattr(self.cfg.background, "color", rgb))
        self.color_row = s.add_row(self.color_label, self.color_btn)

        s.add(separator())
        s.add_hint("Tinh chỉnh biên — hữu ích khi tóc bị ăn mất hoặc lộ viền nền cũ.")

        self.feather_slider = SliderRow("Làm mềm biên", 0.0, 6.0, 0.0, 1, " px")
        self.feather_slider.bind(lambda v: setattr(self.cfg.segmentation, "feather", v))
        s.add(self.feather_slider)

        self.shift_slider = SliderRow("Co / nở vùng người", -1.0, 1.0, 0.0)
        self.shift_slider.bind(lambda v: setattr(self.cfg.segmentation, "shift", v))
        s.add(self.shift_slider)

        self.segcontrast_slider = SliderRow("Độ dứt khoát", 0.0, 1.0, 0.0)
        self.segcontrast_slider.bind(lambda v: setattr(self.cfg.segmentation, "contrast", v))
        s.add(self.segcontrast_slider)

        self.downsample_slider = SliderRow("Tỉ lệ suy luận (0 = tự động)", 0.0, 1.0, 0.0)
        self.downsample_slider.bind(self._on_downsample_changed)
        s.add(self.downsample_slider)
        return s

    def _section_color(self) -> Section:
        s = Section("Màu sắc", expanded=False)
        f = self.cfg.filters
        self.sl_exposure = SliderRow("Phơi sáng", -1.0, 1.0, f.exposure)
        self.sl_contrast = SliderRow("Tương phản", -1.0, 1.0, f.contrast)
        self.sl_saturation = SliderRow("Bão hoà", -1.0, 1.0, f.saturation)
        self.sl_temperature = SliderRow("Nhiệt màu", -1.0, 1.0, f.temperature)
        self.sl_tint = SliderRow("Sắc độ", -1.0, 1.0, f.tint)
        self.sl_gamma = SliderRow("Gamma", -1.0, 1.0, f.gamma)
        for name, widget in (("exposure", self.sl_exposure), ("contrast", self.sl_contrast),
                             ("saturation", self.sl_saturation),
                             ("temperature", self.sl_temperature),
                             ("tint", self.sl_tint), ("gamma", self.sl_gamma)):
            widget.bind(lambda v, n=name: setattr(self.cfg.filters, n, v))
            s.add(widget)

        s.add(separator())
        self.lut_combo = LabeledCombo("LUT")
        self.lut_combo.bind(self._on_lut_changed)
        s.add(self.lut_combo)

        lut_open = QPushButton("Mở file .cube…")
        lut_open.clicked.connect(self._pick_lut)
        s.add(lut_open)

        self.lut_strength = SliderRow("Cường độ LUT", 0.0, 1.0, f.lut_strength)
        self.lut_strength.bind(lambda v: setattr(self.cfg.filters, "lut_strength", v))
        s.add(self.lut_strength)

        reset = QPushButton("Đặt lại màu")
        reset.clicked.connect(self._reset_color)
        s.add(reset)
        return s

    def _section_beauty(self) -> Section:
        s = Section("Làm đẹp", expanded=False)
        b = self.cfg.beauty
        self.sl_smooth = SliderRow("Làm mịn da", 0.0, 1.0, b.smooth)
        self.sl_smooth.bind(lambda v: setattr(self.cfg.beauty, "smooth", v))
        s.add(self.sl_smooth)

        self.skin_toggle = ToggleRow("Chỉ áp lên vùng da", b.skin_only)
        self.skin_toggle.bind(lambda v: setattr(self.cfg.beauty, "skin_only", v))
        s.add(self.skin_toggle)

        self.sl_sharpen = SliderRow("Nét", 0.0, 1.0, b.sharpen)
        self.sl_sharpen.bind(lambda v: setattr(self.cfg.beauty, "sharpen", v))
        s.add(self.sl_sharpen)

        self.sl_vignette = SliderRow("Vignette", 0.0, 1.0, b.vignette)
        self.sl_vignette.bind(lambda v: setattr(self.cfg.beauty, "vignette", v))
        s.add(self.sl_vignette)
        return s

    def _section_frame(self) -> Section:
        s = Section("Khung hình", expanded=False)
        a = self.cfg.autoframe
        self.frame_toggle = ToggleRow("Tự động bám chủ thể", a.enabled)
        self.frame_toggle.bind(self._on_autoframe_toggled)
        s.add(self.frame_toggle)

        self.frame_source = LabeledCombo("Bám theo")
        self.frame_source.bind(lambda v: setattr(self.cfg.autoframe, "source", v))
        s.add(self.frame_source)

        self.sl_zoom = SliderRow("Khoảng đệm", 1.0, 3.0, a.zoom)
        self.sl_zoom.bind(lambda v: setattr(self.cfg.autoframe, "zoom", v))
        s.add(self.sl_zoom)

        self.sl_smoothing = SliderRow("Độ mượt", 0.0, 0.99, a.smoothing)
        self.sl_smoothing.bind(lambda v: setattr(self.cfg.autoframe, "smoothing", v))
        s.add(self.sl_smoothing)

        self.sl_maxzoom = SliderRow("Phóng tối đa", 1.0, 4.0, a.max_zoom, 1, "×")
        self.sl_maxzoom.bind(lambda v: setattr(self.cfg.autoframe, "max_zoom", v))
        s.add(self.sl_maxzoom)
        s.add_hint("«Theo chủ thể» dùng mặt nạ AI nên cần bật tách nền; "
                   "«Theo khuôn mặt» chạy độc lập trên CPU.")
        return s

    def _section_output(self) -> Section:
        s = Section("Đầu ra", expanded=False)
        self.outres_combo = LabeledCombo("Độ phân giải xuất")
        self.outres_combo.bind(self._on_output_res_changed)
        s.add(self.outres_combo)
        s.add_hint("Quay ở độ phân giải cao hơn mức xuất (ví dụ nguồn 1080p → xuất 720p) "
                   "để «Tự động bám chủ thể» cắt khung mà gần như không mất nét.")
        s.add(separator())

        self.vcam_combo = LabeledCombo("Webcam ảo")
        self.vcam_combo.bind(self._on_vcam_device_changed)
        s.add(self.vcam_combo)
        s.add_hint("Thiếu thiết bị? Chạy:  sudo ./scripts/setup_v4l2loopback.sh")

        s.add(separator())
        self.enc_combo = LabeledCombo("Bộ mã hoá")
        self.enc_combo.bind(lambda v: setattr(self.cfg.output, "encoder", v))
        s.add(self.enc_combo)

        self.recfps_combo = LabeledCombo("FPS ghi")
        self.recfps_combo.bind(lambda v: setattr(self.cfg.output, "record_fps", int(v)))
        s.add(self.recfps_combo)

        self.dir_label = QLabel(self.cfg.output.record_dir)
        self.dir_label.setObjectName("Hint")
        self.dir_label.setWordWrap(True)
        pick = QPushButton("Chọn thư mục lưu…")
        pick.clicked.connect(self._pick_record_dir)
        s.add(pick)
        s.add(self.dir_label)
        return s

    # ---------- thanh trạng thái ----------
    def _build_statusbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(34)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(14)

        self.status_label = QLabel("Đang khởi động…")
        self.status_label.setObjectName("Hint")
        lay.addWidget(self.status_label, 1)

        self.stats_label = QLabel("—")
        self.stats_label.setObjectName("Hint")
        self.stats_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.stats_label, 0)
        return bar

    # ================================================================
    # nạp cấu hình vào widget
    # ================================================================
    def _load_from_config(self) -> None:
        self._loading = True
        self._refresh_devices(select_current=True)
        self._rebuild_camera_controls()
        self._refresh_presets()

        models = seg.available_models()
        self.model_combo.set_items(models or ["(chưa có model)"],
                                   models or [""],
                                   self.cfg.segmentation.model)
        self.seg_toggle.set_checked(self.cfg.segmentation.enabled)
        self.bgmode_combo.set_items([n for _, n in BG_MODES], [k for k, _ in BG_MODES],
                                    self.cfg.background.mode)
        self.fit_combo.set_items([n for _, n in FIT_MODES], [k for k, _ in FIT_MODES],
                                 self.cfg.background.image_fit)
        self.frame_source.set_items([n for _, n in FRAME_SOURCES],
                                    [k for k, _ in FRAME_SOURCES],
                                    self.cfg.autoframe.source)
        self.blur_slider.set_value(self.cfg.background.blur)
        self.color_btn.set_rgb(self.cfg.background.color)
        self.feather_slider.set_value(self.cfg.segmentation.feather)
        self.shift_slider.set_value(self.cfg.segmentation.shift)
        self.segcontrast_slider.set_value(self.cfg.segmentation.contrast)
        self.downsample_slider.set_value(self.cfg.segmentation.downsample)
        self.mirror_toggle.set_checked(self.cfg.capture.mirror)
        self._refresh_luts()
        self._sync_color_widgets()

        out_sizes = [(0, 0), (1920, 1080), (1600, 900), (1280, 720), (960, 540), (640, 360)]
        self.outres_combo.set_items(
            ["Như nguồn"] + [f"{w}×{h}" for w, h in out_sizes[1:]], out_sizes,
            (self.cfg.output.width, self.cfg.output.height))

        encoders = available_encoders()
        labels = {"vaapi": "VAAPI (GPU AMD)", "x264": "libx264 (CPU)"}
        self.enc_combo.set_items(["Tự động"] + [labels.get(e, e) for e in encoders],
                                 ["auto"] + encoders, self.cfg.output.encoder)
        fps_values = [15, 24, 30, 60]
        self.recfps_combo.set_items([f"{v} fps" for v in fps_values], fps_values,
                                    self.cfg.output.record_fps)
        self.dir_label.setText(self.cfg.output.record_dir)
        self._loading = False
        self._update_visibility()
        # bảng có thể bị cuộn lệch trong lúc dựng widget — kéo về đầu
        QTimer.singleShot(0, lambda: self._panel_scroll.verticalScrollBar().setValue(0))

    def _sync_color_widgets(self) -> None:
        f = self.cfg.filters
        for widget, value in ((self.sl_exposure, f.exposure), (self.sl_contrast, f.contrast),
                              (self.sl_saturation, f.saturation),
                              (self.sl_temperature, f.temperature),
                              (self.sl_tint, f.tint), (self.sl_gamma, f.gamma),
                              (self.lut_strength, f.lut_strength)):
            widget.set_value(value)
        b = self.cfg.beauty
        self.sl_smooth.set_value(b.smooth)
        self.sl_sharpen.set_value(b.sharpen)
        self.sl_vignette.set_value(b.vignette)
        self.skin_toggle.set_checked(b.skin_only)
        a = self.cfg.autoframe
        self.frame_toggle.set_checked(a.enabled)
        self.sl_zoom.set_value(a.zoom)
        self.sl_smoothing.set_value(a.smoothing)
        self.sl_maxzoom.set_value(a.max_zoom)
        self.bg_image_label.setText(
            Path(self.cfg.background.image_path).name or "Chưa chọn ảnh nền")

    def _update_visibility(self) -> None:
        mode = self.cfg.background.mode
        seg_on = self.cfg.segmentation.enabled
        self.blur_slider.setVisible(mode == "blur" and seg_on)
        self.bg_row.setVisible(mode == "image" and seg_on)
        self.bg_image_label.setVisible(mode == "image" and seg_on)
        self.fit_combo.setVisible(mode == "image" and seg_on)
        self.color_row.setVisible(mode == "color" and seg_on)
        for w in (self.model_combo, self.feather_slider, self.shift_slider,
                  self.segcontrast_slider, self.downsample_slider):
            w.setVisible(seg_on)

    def _refresh_devices(self, select_current: bool = True) -> None:
        cams = list_cameras()
        if cams:
            self.cam_combo.set_items([c.label for c in cams], [c.path for c in cams],
                                     self.cfg.capture.device if select_current else None)
            if self.cam_combo.data() is None:
                self.cam_combo.combo.setCurrentIndex(0)
                self.cfg.capture.device = self.cam_combo.data()
            self._refresh_resolutions(cams)
        else:
            self.cam_combo.set_items(["(không tìm thấy camera)"], [""])

        vdevs = VirtualCamera.available_devices()
        if vdevs:
            self.vcam_combo.set_items(["Tự động"] + [d.label for d in vdevs],
                                      [""] + [d.path for d in vdevs],
                                      self.cfg.output.vcam_device)
        else:
            self.vcam_combo.set_items(["(chưa có v4l2loopback)"], [""])
        usable = [d for d in vdevs if d.can_output]
        self.btn_vcam.setEnabled(bool(usable))
        if vdevs and not usable:
            self.btn_vcam.setToolTip(
                "Thiết bị v4l2loopback đang có không nhận được luồng ghi vào.\n"
                "Chạy: sudo ./scripts/setup_v4l2loopback.sh")
        else:
            self.btn_vcam.setToolTip("")

    def _refresh_resolutions(self, cams=None) -> None:
        cams = cams or list_cameras()
        current = next((c for c in cams if c.path == self.cfg.capture.device), None)
        sizes = current.sizes if current else []
        preferred = [(3840, 2160), (2560, 1440), (1920, 1080), (1600, 900),
                     (1280, 720), (960, 540), (848, 480), (640, 480), (640, 360)]
        listed = [s for s in preferred if s in sizes] or sizes[:8]
        if not listed:
            listed = [(1280, 720), (640, 480)]
        cur = (self.cfg.capture.width, self.cfg.capture.height)
        if cur not in listed:
            listed = sorted(set(listed + [cur]), key=lambda s: -s[0] * s[1])
        self.res_combo.set_items([f"{w}×{h}" for w, h in listed], listed, cur)

        fps_values = [15, 24, 30, 60]
        self.fps_combo.set_items([f"{v} fps" for v in fps_values], fps_values,
                                 self.cfg.capture.fps)
        self.fmt_combo.set_items(["MJPG (fps cao)", "YUYV (không nén)"],
                                 ["MJPG", "YUYV"], self.cfg.capture.fourcc)

    def _refresh_luts(self) -> None:
        luts = builtin_luts()
        names = ["Không dùng"] + list(luts.keys())
        data = [""] + [str(p) for p in luts.values()]
        current = self.cfg.filters.lut_path
        if current and current not in data:
            names.append(Path(current).stem)
            data.append(current)
        self.lut_combo.set_items(names, data, current)

    def _refresh_presets(self) -> None:
        names = cfgmod.list_presets()
        self.preset_combo.set_items(["(tuỳ chỉnh)"] + names, [""] + names, "")

    # ================================================================
    # xử lý sự kiện
    # ================================================================
    def _on_camera_changed(self, path) -> None:
        if self._loading or not path:
            return
        self.cfg.capture.device = path
        self._refresh_resolutions()
        self._rebuild_camera_controls()
        self.pipeline.post("restart_capture")

    def _on_resolution_changed(self, size) -> None:
        if self._loading or not size:
            return
        self.cfg.capture.width, self.cfg.capture.height = size
        self.pipeline.post("restart_capture")

    def _on_fps_changed(self, fps) -> None:
        if self._loading or not fps:
            return
        self.cfg.capture.fps = int(fps)
        self.pipeline.post("restart_capture")

    def _on_format_changed(self, fmt) -> None:
        if self._loading or not fmt:
            return
        self.cfg.capture.fourcc = fmt
        self.pipeline.post("restart_capture")

    def _on_seg_toggled(self, on: bool) -> None:
        self.cfg.segmentation.enabled = on
        self._update_visibility()

    def _on_model_changed(self, name) -> None:
        if self._loading or not name:
            return
        self.cfg.segmentation.model = name
        self.pipeline.post("reload_model")

    def _on_bgmode_changed(self, mode) -> None:
        if not mode:
            return
        self.cfg.background.mode = mode
        self._update_visibility()

    def _on_downsample_changed(self, value: float) -> None:
        self.cfg.segmentation.downsample = 0.0 if value < 0.05 else value
        self.pipeline.post("reset_state")

    def _on_autoframe_toggled(self, on: bool) -> None:
        self.cfg.autoframe.enabled = on
        self.pipeline.post("reset_state")

    def _on_lut_changed(self, path) -> None:
        if self._loading:
            return
        self.cfg.filters.lut_path = path or ""

    def _on_output_res_changed(self, size) -> None:
        if self._loading or size is None:
            return
        self.cfg.output.width, self.cfg.output.height = size
        self.pipeline.post("reset_state")
        self.vcam_restart_needed()

    def vcam_restart_needed(self) -> None:
        """Webcam ảo phải mở lại khi kích thước khung đổi."""
        if self.cfg.output.vcam_enabled:
            self.pipeline.post("vcam")

    def _on_vcam_device_changed(self, path) -> None:
        if self._loading:
            return
        self.cfg.output.vcam_device = path or ""
        if self.cfg.output.vcam_enabled:
            self.pipeline.post("vcam")

    def _on_vcam_toggled(self, on: bool) -> None:
        self.cfg.output.vcam_enabled = on
        self.btn_vcam.setText("Đang phát ra webcam ảo" if on else "Bật webcam ảo")
        self.pipeline.post("vcam")

    def _on_record_toggled(self, on: bool) -> None:
        if on:
            if self._last_frame is None:
                self.btn_record.setChecked(False)
                return
            h, w = self._last_frame.rgb.shape[:2]
            self.pipeline.post("record_start", size=(w, h))
            self.btn_record.setText("⏹  Dừng ghi")
            self.btn_record.setObjectName("Danger")
        else:
            self.pipeline.post("record_stop")
            self.btn_record.setText("⏺  Ghi hình")
            self.btn_record.setObjectName("")
        self.btn_record.style().polish(self.btn_record)

    # ---------- hộp thoại ----------
    def _pick_background_image(self) -> None:
        start = str(ASSET_DIR / "backgrounds")
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh nền", start,
            "Ảnh (*.png *.jpg *.jpeg *.bmp *.webp);;Tất cả (*)")
        if path:
            self._set_background_image(path)

    def _set_background_image(self, path: str) -> None:
        self.cfg.background.image_path = path
        self.bg_image_label.setText(Path(path).name if path else "Chưa chọn ảnh nền")

    def _pick_lut(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn LUT", str(ASSET_DIR / "luts"), "Cube LUT (*.cube);;Tất cả (*)")
        if path:
            self.cfg.filters.lut_path = path
            self._refresh_luts()

    def _pick_record_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Thư mục lưu",
                                                self.cfg.output.record_dir)
        if path:
            self.cfg.output.record_dir = path
            self.dir_label.setText(path)

    def _open_record_dir(self) -> None:
        import subprocess
        Path(self.cfg.output.record_dir).expanduser().mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", self.cfg.output.record_dir])

    # ---------- preset ----------
    def _on_preset_selected(self, _index: int) -> None:
        if self._loading:
            return
        name = self.preset_combo.data()
        if not name:
            return
        cfgmod.load_preset(name, self.cfg)
        self._loading = True
        self.bgmode_combo.set_items([n for _, n in BG_MODES], [k for k, _ in BG_MODES],
                                    self.cfg.background.mode)
        self.blur_slider.set_value(self.cfg.background.blur)
        self.color_btn.set_rgb(self.cfg.background.color)
        self.seg_toggle.set_checked(self.cfg.segmentation.enabled)
        self.feather_slider.set_value(self.cfg.segmentation.feather)
        self.shift_slider.set_value(self.cfg.segmentation.shift)
        self.segcontrast_slider.set_value(self.cfg.segmentation.contrast)
        self._refresh_luts()
        self._sync_color_widgets()
        self._loading = False
        self._update_visibility()
        self.pipeline.post("reset_state")
        self._set_status(f"Đã nạp preset “{name}”", 0)

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Lưu preset", "Tên preset:")
        name = (name or "").strip()
        if not ok or not name:
            return
        cfgmod.save_preset(name, self.cfg)
        self._loading = True
        self._refresh_presets()
        self.preset_combo.set_current(name)
        self._loading = False
        self._set_status(f"Đã lưu preset “{name}”", 0)

    def _delete_preset(self) -> None:
        name = self.preset_combo.data()
        if not name:
            return
        if QMessageBox.question(self, "Xoá preset", f"Xoá preset “{name}”?") == \
                QMessageBox.StandardButton.Yes:
            cfgmod.delete_preset(name)
            self._loading = True
            self._refresh_presets()
            self._loading = False

    def _reset_color(self) -> None:
        from ..config import FilterConfig
        keep = self.cfg.filters.lut_path
        self.cfg.filters.__dict__.update(FilterConfig().__dict__)
        self.cfg.filters.lut_path = keep
        self._loading = True
        self._sync_color_widgets()
        self._loading = False

    def _reset_all(self) -> None:
        if QMessageBox.question(self, "Đặt lại", "Đưa mọi thiết lập về mặc định?") != \
                QMessageBox.StandardButton.Yes:
            return
        device = self.cfg.capture.device
        self.cfg.apply_dict(AppConfig().to_dict())
        self.cfg.capture.device = device
        self._load_from_config()
        self.pipeline.post("reset_state")

    # ================================================================
    # kết nối pipeline
    # ================================================================
    def _connect_pipeline(self) -> None:
        self.pipeline.frameReady.connect(self._on_frame, Qt.QueuedConnection)
        self.pipeline.statsReady.connect(self._on_stats, Qt.QueuedConnection)
        self.pipeline.status.connect(self._set_status, Qt.QueuedConnection)

    def _on_frame(self, frame: Frame) -> None:
        self._last_frame = frame
        self.preview.set_frame(frame.rgb, frame.alpha)

    def _on_stats(self, s: Stats) -> None:
        parts = [f"{s.capture_fps:.0f} fps vào",
                 f"{s.process_fps:.0f} fps ra",
                 f"GPU {s.gpu_ms:.1f} ms",
                 s.resolution,
                 f"VRAM {s.vram_mb:.0f} MB"]
        if s.vcam:
            parts.append(f"→ {s.vcam}")
        if s.recording:
            m, sec = divmod(int(s.rec_seconds), 60)
            parts.append(f"⏺ {m:02d}:{sec:02d}")
        self.stats_label.setText("   ·   ".join(parts))

    def _set_status(self, message: str, level: int = 0) -> None:
        color = (style.TEXT_DIM, style.WARN, style.ERR)[max(0, min(2, level))]
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(message.replace("\n", " ").strip()[:200])
        self.status_label.setToolTip(message)
        if level == 0:
            QTimer.singleShot(6000, lambda: self.status_label.setText(""))

    # ================================================================
    def _register_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+R"), self, lambda: self.btn_record.toggle())
        QShortcut(QKeySequence("Ctrl+S"), self, lambda: self.pipeline.post("snapshot"))
        QShortcut(QKeySequence("Ctrl+B"), self, lambda: self.btn_vcam.toggle())
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    def closeEvent(self, event: QCloseEvent) -> None:      # noqa: N802 (Qt API)
        self.pipeline.stop()
        if self._cam_controls is not None:
            self._cam_controls.close()
        try:
            self.cfg.save()
        except OSError:
            pass
        super().closeEvent(event)

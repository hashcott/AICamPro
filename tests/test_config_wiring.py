"""Mỗi thiết lập trong AppConfig phải thực sự làm đổi khung hình đầu ra.

Có lần `BackgroundCompositor.set_image()` không được gọi ở đâu cả: giao diện đặt
`background.image_path` nhưng pipeline chẳng bao giờ nạp ảnh, và `_background_for`
lặng lẽ rơi xuống nhánh màu đặc. Không có lỗi, không có cảnh báo — chỉ là tính năng
không chạy. Bộ test này chạy khung hình qua đúng `Pipeline._process` và đòi hỏi
từng thiết lập phải để lại dấu vết trên ảnh ra.
"""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytestmark = pytest.mark.skipif(not torch.cuda.is_available(),
                                reason="cần GPU (ROCm/CUDA)")

from procam.config import ASSET_DIR, AppConfig          # noqa: E402
from procam.core.pipeline import Pipeline               # noqa: E402
from procam.gpu import segmentation as seg              # noqa: E402
from procam.gpu.compose import BackgroundCompositor     # noqa: E402
from procam.gpu.filters import FilterStack              # noqa: E402

BG_IMAGE = ASSET_DIR / "backgrounds" / "02_sunset_gradient.jpg"
LUT = ASSET_DIR / "luts" / "02_cool_cinema.cube"


SUBJECT = ((246, 200), (394, 360))      # thân, toạ độ pixel
HEAD = ((320, 130), (58, 74))            # đầu: tâm, bán trục


@pytest.fixture(scope="module")
def frame() -> np.ndarray:
    """Khung hình tổng hợp: 'người' màu da, có vân, trên nền tối kẻ ô."""
    import cv2
    rng = np.random.default_rng(3)
    img = np.full((360, 640, 3), 40, np.uint8)
    for x in range(0, 640, 40):
        cv2.line(img, (x, 0), (x, 360), (70, 60, 55), 2)
    for y in range(0, 360, 40):
        cv2.line(img, (0, y), (640, y), (70, 60, 55), 2)
    cv2.ellipse(img, HEAD[0], HEAD[1], 0, 0, 360, (150, 175, 205), -1)
    cv2.rectangle(img, *SUBJECT, (150, 175, 205), -1)
    # vân nhẹ để bộ lọc làm nét / làm mịn có cái để tác động
    noise = rng.integers(-12, 13, img.shape, dtype=np.int16)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


class FakeMatter(seg.Matter):
    """Alpha xác định trước.

    Không dùng RVM trong test nối dây: model được huấn luyện trên người thật nên
    với hình vẽ nó trả alpha ~0, khiến mọi thiết lập phụ thuộc alpha đều "không
    tác động" và test hoá ra chỉ đang đo giới hạn của model. Ở đây cần kiểm tra
    dây nối, nên alpha phải chắc chắn và lặp lại được.
    """

    name = "fake"

    def alpha(self, rgb):
        import torch
        h, w = rgb.shape[-2:]
        a = torch.zeros((1, 1, h, w), device=rgb.device)
        (x0, y0), (x1, y1) = SUBJECT
        sx, sy = w / 640, h / 360
        a[..., int(y0 * sy):int(y1 * sy), int(x0 * sx):int(x1 * sx)] = 1.0
        cx, cy = HEAD[0][0] * sx, HEAD[0][1] * sy
        rx, ry = HEAD[1][0] * sx, HEAD[1][1] * sy
        ys = torch.arange(h, device=rgb.device).view(1, 1, h, 1).float()
        xs = torch.arange(w, device=rgb.device).view(1, 1, 1, w).float()
        head = (((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2) <= 1.0
        a = torch.maximum(a, head.float())
        # biên mềm như alpha thật, nếu không các thiết lập chỉnh biên sẽ vô hiệu
        from procam.gpu import ops
        a = ops.gaussian_blur(a, 2.5).clamp(0, 1)
        return a, rgb * a          # fgr: chủ thể đã tách khỏi nền


def run(cfg: AppConfig, frame: np.ndarray, real_model: bool = False) -> np.ndarray:
    pipe = Pipeline(cfg)
    dev = pipe.info.torch_device
    pipe.compositor = BackgroundCompositor(dev)
    pipe.filters = FilterStack(dev)
    pipe.matter = (seg.create_matter(cfg.segmentation.model, dev) if real_model
                   else FakeMatter())
    pipe._matter_name = cfg.segmentation.model      # chặn _ensure_matter thay mất
    return pipe._process(frame).rgb


def baseline() -> AppConfig:
    cfg = AppConfig()
    cfg.background.mode = "blur"
    return cfg


# (tên, hàm chỉnh cấu hình) — mỗi cái phải làm đổi ảnh so với baseline
CASES = [
    ("background.mode=image", lambda c: (setattr(c.background, "mode", "image"),
                                         setattr(c.background, "image_path", str(BG_IMAGE)))),
    ("background.mode=color", lambda c: setattr(c.background, "mode", "color")),
    ("background.mode=greenscreen", lambda c: setattr(c.background, "mode", "greenscreen")),
    ("background.mode=none", lambda c: setattr(c.background, "mode", "none")),
    ("background.blur", lambda c: setattr(c.background, "blur", 1.0)),
    ("background.color", lambda c: (setattr(c.background, "mode", "color"),
                                    setattr(c.background, "color", (255, 0, 128)))),
    ("background.image_fit", lambda c: (setattr(c.background, "mode", "image"),
                                        setattr(c.background, "image_path", str(BG_IMAGE)),
                                        setattr(c.background, "image_fit", "contain"))),
    ("segmentation.feather", lambda c: setattr(c.segmentation, "feather", 5.0)),
    ("segmentation.shift", lambda c: setattr(c.segmentation, "shift", 0.9)),
    ("segmentation.contrast", lambda c: setattr(c.segmentation, "contrast", 1.0)),
    ("segmentation.enabled=False", lambda c: setattr(c.segmentation, "enabled", False)),
    ("filters.exposure", lambda c: setattr(c.filters, "exposure", 0.6)),
    ("filters.contrast", lambda c: setattr(c.filters, "contrast", 0.6)),
    ("filters.saturation", lambda c: setattr(c.filters, "saturation", -0.9)),
    ("filters.temperature", lambda c: setattr(c.filters, "temperature", 0.8)),
    ("filters.tint", lambda c: setattr(c.filters, "tint", 0.8)),
    ("filters.gamma", lambda c: setattr(c.filters, "gamma", 0.8)),
    ("filters.lut_path", lambda c: setattr(c.filters, "lut_path", str(LUT))),
    ("beauty.smooth", lambda c: setattr(c.beauty, "smooth", 1.0)),
    ("beauty.sharpen", lambda c: setattr(c.beauty, "sharpen", 1.0)),
    ("beauty.vignette", lambda c: setattr(c.beauty, "vignette", 1.0)),
    ("autoframe.enabled", lambda c: (setattr(c.autoframe, "enabled", True),
                                     setattr(c.autoframe, "smoothing", 0.0))),
    ("capture.mirror=False", lambda c: setattr(c.capture, "mirror", False)),
]


@pytest.mark.parametrize("name,mutate", CASES, ids=[c[0] for c in CASES])
def test_setting_changes_output(name, mutate, frame):
    base = run(baseline(), frame)
    cfg = baseline()
    mutate(cfg)
    got = run(cfg, frame)

    if name == "capture.mirror=False":
        # lật gương do luồng đọc camera làm, không thuộc _process
        pytest.skip("mirror áp ở CameraCapture, không phải trong _process")

    assert got.shape == base.shape, f"{name}: đổi kích thước ngoài ý muốn"
    diff = np.abs(got.astype(np.int16) - base.astype(np.int16)).mean()
    # `_process` chạy tất định (xem test_pipeline_is_deterministic), nên một thiết
    # lập không được nối dây sẽ cho sai khác đúng bằng 0. Ngưỡng nhỏ là đủ để bắt.
    assert diff > 0.01, f"{name}: không tác động gì tới ảnh ra (sai khác {diff:.3f}/255)"


def test_pipeline_is_deterministic(frame):
    """Cùng cấu hình phải cho ra khung hình y hệt — cơ sở cho ngưỡng ở test trên."""
    a = run(baseline(), frame)
    b = run(baseline(), frame)
    assert np.array_equal(a, b)


def test_output_resolution_applies(frame):
    cfg = baseline()
    cfg.output.width, cfg.output.height = 320, 180
    assert run(cfg, frame).shape[:2] == (180, 320)


def test_transparent_mode_emits_alpha(frame):
    cfg = baseline()
    cfg.background.mode = "transparent"
    pipe = Pipeline(cfg)
    dev = pipe.info.torch_device
    pipe.compositor = BackgroundCompositor(dev)
    pipe.filters = FilterStack(dev)
    pipe.matter = FakeMatter()
    pipe._matter_name = cfg.segmentation.model
    out = pipe._process(frame)
    assert out.alpha is not None and out.alpha.shape == frame.shape[:2]


def test_missing_background_image_warns(frame):
    cfg = baseline()
    cfg.background.mode = "image"
    cfg.background.image_path = "/khong/ton/tai.jpg"
    pipe = Pipeline(cfg)
    dev = pipe.info.torch_device
    pipe.compositor = BackgroundCompositor(dev)
    pipe.filters = FilterStack(dev)
    pipe.matter = FakeMatter()
    pipe._matter_name = cfg.segmentation.model
    msgs: list[tuple[int, str]] = []
    pipe.status.connect(lambda m, lv: msgs.append((lv, m)))
    pipe._process(frame)
    assert any(lv >= 1 for lv, _ in msgs), "thiếu ảnh nền mà không cảnh báo gì"

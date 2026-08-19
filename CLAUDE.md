# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Ngôn ngữ

Repo này viết tài liệu, comment và mọi chuỗi hiển thị trên GUI bằng **tiếng Việt**;
tên định danh trong code giữ tiếng Anh. Giữ nguyên quy ước này khi thêm code mới.

## Lệnh thường dùng

Mọi thứ chạy trong môi trường conda `soi` (Python 3.12 + PyTorch ROCm):

```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda activate soi
```

| Việc | Lệnh |
|---|---|
| Chạy app | `./run.sh` (tự activate conda rồi `python -m soi`) |
| Kiểm tra GPU / model / thiết bị | `./run.sh --check` |
| Liệt kê camera + webcam ảo | `./run.sh --list-devices` |
| Dựng lại môi trường | `./scripts/setup_env.sh` |
| Tải model tách nền | `./scripts/download_models.sh [all]` |
| Tạo thiết bị webcam ảo (một lần, cần sudo) | `sudo ./scripts/setup_v4l2loopback.sh` |
| Sinh lại LUT + ảnh nền mẫu | `python scripts/make_assets.py` |
| Cổng kiểm tra cú pháp nhanh | `python -m compileall -q soi` |
| Lint | `ruff check soi` (line-length 100, cấu hình trong `pyproject.toml`) |

**Test:** `python -m pytest tests/` (26 test, ~8 giây, cần GPU — tự bỏ qua nếu không có).
Chạy một test: `python -m pytest "tests/test_config_wiring.py::test_setting_changes_output[filters.gamma]"`.

`tests/test_config_wiring.py` chạy khung hình tổng hợp qua đúng `Pipeline._process`
và đòi hỏi **mỗi** trường trong `AppConfig` phải để lại dấu vết trên ảnh ra. Nó tồn
tại vì `BackgroundCompositor.set_image()` từng không được gọi ở đâu cả: giao diện đặt
`background.image_path`, pipeline không bao giờ nạp ảnh, `_background_for` lặng lẽ rơi
xuống nhánh màu đặc — không lỗi, không cảnh báo, tính năng chỉ đơn giản là không chạy.
**Thêm trường cấu hình mới thì thêm luôn một dòng vào `CASES`.**

Test dùng `FakeMatter` chứ không dùng RVM: model huấn luyện trên người thật nên với
hình vẽ nó trả alpha ≈ 0, khiến mọi thiết lập phụ thuộc alpha đều "không tác động" và
bài test hoá ra chỉ đang đo giới hạn của model thay vì kiểm tra dây nối.

Cách xác minh thủ công thêm:

- Đo pipeline không cần GUI: viết script ngắn ghép `CameraCapture` →
  `create_matter` → `BackgroundCompositor` → `FilterStack` → `AutoFramer`, xuất ảnh
  ra file rồi xem bằng mắt. Đây là cách nhanh nhất để kiểm tra thay đổi trong `gpu/`.
- Kiểm tra GUI: chạy `python -m soi` rồi
  `import -window $(xdotool search --name 'Soi — ' | head -1) out.png`.
  Cửa sổ có tên bắt đầu bằng `Soi` nhưng chỉ cửa sổ `Soi — …` là cửa sổ thật;
  còn một cửa sổ phụ 1×1 cùng tên `Soi` (`import -window` sẽ thất bại trên nó).
- Chỉ có **một** camera vật lý, và nó không mở được hai lần. Tắt GUI trước khi
  chạy script đọc camera: `pgrep -f "\-m proca[m]" | xargs -r kill`.
  (Đừng dùng `pkill -f "python -m soi"` — chuỗi đó khớp với chính lệnh shell
  đang chạy nên sẽ tự kill luôn.)

## Kiến trúc

### Ba luồng, một chiều dữ liệu

```
luồng đọc camera        luồng xử lý (QThread)              luồng Qt (GUI)
CameraCapture._loop  →  Pipeline.run  ──frameReady──────→  MainWindow._on_frame
 giữ khung mới nhất      sở hữu toàn bộ object GPU          ──post(cmd)──→ hàng lệnh
 + bộ đếm seq                                              mutate AppConfig trực tiếp
```

- **GUI không bao giờ chạm vào object GPU.** Giao tiếp GUI → pipeline đi qua
  `Pipeline.post(name, **kwargs)` (hàng đợi lệnh, xử lý ở đầu mỗi vòng lặp).
- `AppConfig` là **object dùng chung, mutable**. GUI gán thẳng các giá trị scalar
  (slider, toggle) và pipeline đọc lại ở từng khung — không cần lệnh. Chỉ những
  thay đổi mang tính cấu trúc mới cần `post`: `restart_capture`, `reload_model`,
  `reset_state`, `vcam`, `record_start/stop`, `snapshot`.
- `CameraCapture` chỉ giữ khung **mới nhất** (không hàng đợi), nên pipeline chậm
  sẽ bỏ khung chứ không tăng độ trễ.

### Quy ước tensor trong `soi/gpu/`

Mọi hàm nhận và trả `(1, 3, H, W)` float 0..1 thứ tự **RGB**; alpha là `(1, 1, H, W)`.
Camera trả BGR uint8 HWC. Việc chuyển đổi xảy ra đúng **một lần** ở đầu và cuối
`Pipeline._process` — đừng chèn thêm chuyển đổi ở giữa.

### Một lần chuyển GPU → CPU cho mỗi khung

`_process` tải về đúng một mảng RGB uint8. `_dispatch` dùng chung mảng đó cho
preview, webcam ảo và ghi hình (BGR lấy bằng `[:, :, ::-1]`). Thêm bất kỳ lệnh
`.cpu()` nào ở giữa pipeline là thêm một lần đồng bộ GPU cho mỗi khung.

### Thứ tự xử lý trong `Pipeline._process` là có chủ ý

```
tách nền → ghép nền → auto-frame → filter màu → làm đẹp
```

`AutoFramer.apply` cắt **cả ảnh lẫn alpha** và trả về alpha đã cắt. Filter làm đẹp
dùng alpha đó làm mặt nạ chủ thể — dùng alpha trước khi cắt sẽ lệch. `apply` cũng là
nơi duy nhất quyết định kích thước đầu ra (`Pipeline._output_size`), kể cả khi
auto-frame tắt.

`need_mask` bỏ qua hẳn khâu tách nền khi chế độ nền là `none` và auto-frame không
bám theo mặt nạ. Đó là đường nhanh (~0.65 ms/khung so với ~5 ms).

### Tách nền là mạng hồi tiếp

`RVMMatter` giữ trạng thái `_rec` giữa các khung — đó là lý do alpha ổn định,
không nhấp nháy. Trạng thái **phải** được reset khi đổi độ phân giải (tự động qua
`_last_shape`) hoặc đổi model/tỉ lệ suy luận (`post("reset_state")`). Bản fp16 được
nhận biết qua tên file chứa `fp16`. `downsample_ratio` mặc định tính tự động
`512 / max(h, w)`.

### Cấu hình

`AppConfig` là cây dataclass, lưu ở `~/.config/soi/config.json`, preset ở
`~/.config/soi/presets/`. `_merge` khoan dung: bỏ qua khoá lạ, ép kiểu, không
làm hỏng config khi thêm trường mới. Preset cố tình **không** lưu `output` và
`capture.device` để chia sẻ được giữa máy khác nhau. Đường dẫn tương đối (ảnh nền,
LUT) đi qua `resolve_asset()` — thử theo CWD rồi tới gốc repo.

## Cạm bẫy đã gặp

Những thứ này đã tốn thời gian debug một lần, đừng lặp lại:

- **Đừng nhân tỉ lệ khung hình vào hai đại lượng đã chuẩn hoá theo hai trục khác
  nhau.** Trong `AutoFramer`, `want_w` là phần của chiều rộng còn `want_h` là phần
  của chiều cao; `want_w = want_h * aspect` khiến khung cắt có tỉ lệ `aspect²` và ảnh
  bị kéo dãn 1.78 lần. Khung cắt phải được tính bằng **pixel** theo tỉ lệ của đầu ra.
- **Phóng to phá chất lượng nhanh hơn mọi khâu khác**: zoom 1.5× ở 720p làm độ nét
  rớt 5 lần. Dùng `bicubic` khi phóng, `area` khi thu (`autoframe.resize_to`), và
  khuyến khích người dùng đặt nguồn cao hơn đầu ra.
- **Không bao giờ đặt `background` trong quy tắc QSS `QWidget { }`.** Qt áp nó cho
  *mọi* widget con: QLabel tự tô một hình chữ nhật tối đè lên nền panel, QSlider tô
  kín cả ô rồi nuốt luôn kích thước `::groove` và `::handle` (handle ra hình vuông
  thay vì tròn). Chỉ đặt nền cho đúng vùng chứa cần nó, và cho QLabel/QSlider
  `background: transparent`.
- **QSS không hiểu mẹo vẽ tam giác bằng `border-left/right/top` của CSS.**
  `QComboBox::down-arrow` chỉ nhận `image: url(...)`. `style._arrow_icon()` vẽ sẵn
  một PNG vào `~/.cache/soi/` nên không phải kèm file ảnh vào repo — vì thế
  stylesheet là hàm `build_stylesheet()`, phải gọi **sau** khi có QApplication.
- **QSS không tạo được núm trượt cho `QCheckBox::indicator`** — chỉ đổi được màu nền
  nên công tắc trông như viên thuốc đặc. `ToggleSwitch` tự vẽ bằng QPainter.
- **Đừng kiểm tra lớp cụ thể ở chỗ đã có giao diện.** `_process` từng viết
  `isinstance(self.matter, seg.RVMMatter)`, nghĩa là mọi backend tách nền khác sẽ bị
  bỏ qua trong im lặng. Dùng `Matter` và thêm phương thức vào giao diện
  (`Matter.configure`) thay vì hỏi lớp nào.
- **Thứ nguy hiểm nhất là tính năng hỏng mà không kêu.** Nhánh dự phòng nên nói ra:
  `Pipeline._sync_background` phát cảnh báo khi ở chế độ ảnh mà chưa có ảnh, thay vì
  âm thầm vẽ màu đặc.
- **`CAP_PROP_BUFFERSIZE = 1` làm tụt một nửa fps** với backend V4L2 (30 → 16 fps).
  Dùng `2`.
- **PySide6 `QComboBox.findData()` so sánh object Python theo identity**, không theo
  giá trị — tuple `(1280, 720)` dựng lúc chạy không bao giờ khớp với tuple cùng giá
  trị trong combo. Dùng `LabeledCombo._select()` / `.set_current()` thay vì `findData`.
- **Số hiệu ioctl phải khớp `dir` và kích thước struct**, sai một chút là `ENOTTY`.
  `VIDIOC_QUERYCAP` là `_IOR` (dir=2, 104 byte); `VIDIOC_ENUM_FRAMESIZES` là `_IOWR`
  (dir=3, 44 byte); `G_CTRL`/`S_CTRL` là `_IOWR` 8 byte; `QUERYCTRL` `_IOWR` 68 byte.
- **Combo và slider nằm trong `QScrollArea` phải chặn wheel** khi chưa focus, nếu
  không cuộn bảng sẽ vô tình đổi giá trị. Dùng `SafeComboBox` / `SafeSlider`.
- **`QPushButton.clicked` truyền `checked: bool`** — đừng nối thẳng vào hàm có tham
  số đầu mang ý nghĩa (đã từng làm `_refresh_devices(select_current=False)`).
- **Thiết lập phơi sáng / cân bằng trắng do camera UVC lưu trên chính thiết bị**,
  không phải trong app. Script benchmark đặt phơi sáng thủ công sẽ khiến hình tối ở
  mọi lần chạy sau, kể cả sau khi khởi động lại app. Dùng
  `CameraControls.auto_exposure_on()` hoặc `reset_defaults()` để trả lại.
- **`modprobe` trên module ĐÃ nạp bỏ qua toàn bộ tham số, không báo lỗi.** Muốn đổi
  cấu hình v4l2loopback bắt buộc phải `modprobe -r` rồi nạp lại — và việc đó chỉ
  thành công khi refcount trong `/proc/modules` bằng 0.
- **modprobe đọc mọi file trong `/etc/modprobe.d` theo thứ tự abc, file SAU ghi đè
  file trước.** Máy có thể đã có cấu hình v4l2loopback của OBS/Iriun/ProVCam; file
  của Soi đặt tên `zz-…` để đọc sau cùng và phải **gộp** cả thiết bị của các
  ứng dụng kia, nếu không sẽ làm mất webcam ảo của chúng.
- **Thiết bị v4l2loopback có thể khai báo KHÔNG có cả CAPTURE lẫn OUTPUT** (thấy
  `caps=0x05200000` trên thiết bị của OBS). Lúc đó không ứng dụng nào ghi vào được,
  kể cả ffmpeg — không phải lỗi của pyvirtualcam. `V4L2Device.can_output` dùng để
  lọc; script setup tự thử lại với `exclusive_caps=0` nếu bản `=1` không dùng được.
- **Script setup phải kiểm chứng rồi mới báo thành công.** Bản đầu tiên in
  "✓ sẵn sàng" trong khi chẳng tạo được thiết bị nào.
- **Số hiệu `/dev/dri/renderD*` không cố định.** `recorder.py` dò card AMD theo
  `vendor == 0x1002` chứ không giả định `renderD128`.

## Nhập cấu hình từ agent khác

Máy này có `~/.codex/config.toml` và thư mục `~/.gemini/`. Nếu muốn mang MCP server,
slash command, subagent hay skill từ đó sang Claude Code, trả lời `/import` để quét
và xem danh sách những gì nhập được, rồi `/import --yes=<digest>` để áp dụng
(digest hiện trong kết quả quét). Nếu `/import` không có trên giao diện đang dùng,
chạy `claude import` từ terminal.

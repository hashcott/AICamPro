# AICamPro

Webcam AI cho Linux, tăng tốc bằng **GPU AMD qua ROCm**: xoá / làm mờ / thay nền,
bộ lọc màu và làm đẹp, tự động bám chủ thể, xuất ra **webcam ảo** dùng được trong
Google Meet, Zoom, Discord, OBS…

Toàn bộ khâu xử lý ảnh chạy trên GPU bằng PyTorch — CPU chỉ lo đọc camera và giao diện.

*[English](README.md)*

---

## Hiệu năng đo trên máy này

RX 7900 XT (gfx1100) · torch 2.9.1+rocm6.4 · nguồn 1280×720:

| Chế độ | Thời gian / khung | Tương đương |
|---|---|---|
| Chỉ tách nền (RVM mobilenetv3) | 3.8 ms | ~265 fps |
| Làm mờ nền | 5.1 ms | ~198 fps |
| Thay ảnh nền | 4.8 ms | ~210 fps |
| Nền + màu + làm đẹp + vignette | 8.0 ms | ~124 fps |
| Tách nền ở 1920×1080 | 3.9 ms | ~257 fps |

VRAM dùng: **~55 MB**. Nói cách khác card còn dư rất nhiều tài nguyên —
nút cổ chai là chính cái webcam (30 fps), không phải GPU.

---

## Cài đặt

Không bản nào kèm sẵn PyTorch. Bản ROCm chiếm khoảng **14 GB sau khi cài** — 13 GB
trong đó là thư viện ROCm nằm trong wheel — và phải khớp driver amdgpu trên máy,
nên mọi cách cài đều tải nó một lần vào `~/.local/share/aicampro/`.

### AppImage — chạy trên mọi bản phân phối

```bash
VERSION=0.1.1
curl -LO https://github.com/hashcott/AICamPro/releases/download/v$VERSION/AICamPro-$VERSION-x86_64.AppImage
chmod +x AICamPro-*.AppImage
./AICamPro-*.AppImage --setup     # một lần: PyTorch ROCm + model
./AICamPro-*.AppImage
```

Đã mang sẵn Python, Qt, OpenCV, numpy bên trong.

### Debian / Ubuntu / Mint

```bash
VERSION=0.1.1
curl -LO https://github.com/hashcott/AICamPro/releases/download/v$VERSION/aicampro_${VERSION}_all.deb
sudo apt install ./aicampro_${VERSION}_all.deb
aicampro-setup                    # một lần: PyTorch ROCm + Qt + model
aicampro
```

Có sẵn biểu tượng trong menu ứng dụng và trang man `aicampro(1)`.

### Từ mã nguồn

```bash
git clone https://github.com/hashcott/AICamPro.git
cd AICamPro
./scripts/setup_env.sh              # env conda "aicampro" + PyTorch ROCm
./scripts/download_models.sh        # ~23 MB; thêm "all" để lấy cả bản resnet50
./run.sh
```

### Webcam ảo

Cần bước này thì Meet/Zoom/Discord/OBS mới thấy AICamPro. Chạy một lần:

```bash
sudo ./scripts/setup_v4l2loopback.sh                    # bản clone
sudo /usr/lib/aicampro/scripts/setup_v4l2loopback.sh    # bản .deb
```

Kiểm tra nhanh trước khi chạy:

```bash
./run.sh --check          # GPU, model, camera, webcam ảo
./run.sh --list-devices   # chỉ liệt kê thiết bị
```

### Yêu cầu

- GPU AMD được ROCm hỗ trợ (RDNA2/RDNA3 trở lên) + driver `amdgpu`
- Người dùng thuộc nhóm `video` và `render` — kiểm tra bằng `id`;
  nếu thiếu: `sudo usermod -aG video,render $USER` rồi đăng xuất/đăng nhập lại
- `ffmpeg` (để ghi hình) và `v4l2loopback-dkms` (webcam ảo)

Không có GPU AMD? Ứng dụng vẫn chạy trên CPU nhưng chậm hơn nhiều — chỉ hợp để thử.

---

## Tính năng

**Nền** — làm mờ kiểu bokeh, thay bằng ảnh, màu đặc, phông xanh ảo, hoặc nền
trong suốt (xuất PNG có alpha khi chụp ảnh). Có thanh tinh chỉnh biên: làm mềm,
co/nở vùng người, tăng độ dứt khoát — hữu ích khi tóc bị ăn mất hoặc lộ viền nền cũ.

**Màu sắc** — phơi sáng, tương phản, bão hoà, nhiệt màu, sắc độ, gamma, cùng
LUT 3D `.cube` (kèm sẵn 6 preset trong `aicampro/assets/luts/`). Thả file `.cube` bất kỳ
vào thư mục đó là dùng được.

**Làm đẹp** — làm mịn da giữ biên (chỉ áp lên vùng da nếu muốn), tăng nét, vignette.

**Khung hình** — tự động bám chủ thể, cắt và phóng theo người trong ảnh. Bám theo
mặt nạ AI (chính xác nhất) hoặc theo khuôn mặt qua YuNet/Haar khi tắt tách nền.
Khung cắt luôn giữ đúng tỉ lệ đầu ra nên ảnh không bị méo. Muốn bám khung mà không
mất nét thì đặt **Độ phân giải xuất** (mục Đầu ra) thấp hơn độ phân giải nguồn —
ví dụ quay 1080p, xuất 720p: lúc đó khung cắt vẫn còn đủ điểm ảnh thật.

**Camera (phần cứng)** — phơi sáng tự động/thủ công, thời gian phơi sáng, gain,
độ sáng, cân bằng trắng, bù ngược sáng… đọc thẳng từ V4L2 nên chỉ hiện những thứ
camera thực sự hỗ trợ. Có nút đặt lại mặc định.

**Đầu ra** — webcam ảo qua v4l2loopback, ghi video (ưu tiên mã hoá phần cứng
VAAPI trên chính card AMD), chụp ảnh. Preset lưu/nạp được toàn bộ thiết lập.

### Phím tắt

| Phím | Tác dụng |
|---|---|
| `Ctrl+B` | Bật/tắt webcam ảo |
| `Ctrl+R` | Bắt đầu / dừng ghi hình |
| `Ctrl+S` | Chụp ảnh |
| `Ctrl+Q` | Thoát |

---

## Test

```bash
python -m pytest tests/      # cần GPU, ~8 giây
```

`tests/test_config_wiring.py` bắt buộc mỗi thiết lập trong `AppConfig` phải thực sự
làm đổi khung hình ra. Thêm thiết lập mới nhớ thêm một dòng vào `CASES`.

## Kiến trúc

```
aicampro/
├── core/
│   ├── v4l2.py        truy vấn thiết bị qua ioctl (không cần v4l-utils)
│   ├── capture.py     luồng đọc camera, luôn giữ khung mới nhất
│   ├── pipeline.py    luồng xử lý chính (QThread) — điều phối toàn bộ
│   ├── vcam.py        xuất ra v4l2loopback
│   └── recorder.py    ghi video qua ffmpeg + chụp ảnh
├── gpu/               mọi thứ chạy trên GPU, tensor (1,3,H,W) RGB 0..1
│   ├── device.py      dò GPU ROCm
│   ├── ops.py         blur, dilate/erode, mặt nạ da, resize…
│   ├── segmentation.py RobustVideoMatting (TorchScript) + hậu xử lý alpha
│   ├── compose.py     ghép chủ thể lên nền mới
│   ├── filters.py     màu + làm đẹp
│   └── lut.py         nạp/áp LUT .cube bằng grid_sample 3D
├── vision/autoframe.py bám chủ thể (mặt nạ hoặc khuôn mặt)
└── ui/                PySide6: preview, bảng điều khiển, theme tối
```

Luồng dữ liệu một khung hình:

```
camera → BGR (CPU) → tensor GPU → tách nền → ghép nền → auto-frame
       → filter màu → làm đẹp → về CPU một lần duy nhất
       → preview + webcam ảo + ghi hình
```

Chỉ có **một** lần chuyển dữ liệu GPU→CPU cho mỗi khung; preview, webcam ảo và
file ghi đều dùng chung mảng đó.

Model tách nền là [RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting)
— mạng hồi tiếp, nên alpha ổn định theo thời gian thay vì nhấp nháy như các model
tách từng khung độc lập. Trạng thái hồi tiếp được reset khi đổi độ phân giải hoặc model.

Cấu hình lưu tại `~/.config/aicampro/config.json`, preset tại `~/.config/aicampro/presets/`.

---

## Ghi chú kỹ thuật

Vài thứ đã đo được trên chính máy này, ghi lại để khỏi phải tìm lại:

- **`CAP_PROP_BUFFERSIZE = 1` làm tụt một nửa fps** với backend V4L2 (30 → 16 fps).
  Dùng `2`: vẫn giữ độ trễ một khung mà không mất fps.
- **PySide6 `QComboBox.findData()` so sánh object Python theo identity**, không theo
  giá trị. Tuple `(1280, 720)` dựng lúc chạy sẽ không khớp với tuple cùng giá trị đã
  lưu trong combo. `LabeledCombo._select()` tự so sánh bằng `==` để tránh chuyện này.
- **Webcam ảo của OBS (`exclusive_caps=1`) không nhận ghi từ ứng dụng khác.**
  Hãy tạo thiết bị riêng cho AICamPro bằng `scripts/setup_v4l2loopback.sh`.
- **Thiết lập phơi sáng/WB do camera UVC lưu trên chính thiết bị**, không phải trong
  ứng dụng — đặt phơi sáng thủ công rồi thoát app thì lần sau mở lên hình vẫn tối.
  AICamPro phát hiện trạng thái này lúc khởi động và cảnh báo.
- **Quy tắc QSS `QWidget { background: … }` phá giao diện Qt.** Nó áp cho mọi widget
  con nên QLabel hiện thành ô tối, còn QSlider nuốt kích thước groove/handle. Nền
  chỉ đặt cho vùng chứa; QLabel và QSlider để `transparent`.
- **Phóng to là thứ phá chất lượng mạnh nhất trong pipeline.** Đo trên 720p: zoom
  1.5× làm độ nét (phương sai Laplacian) rớt từ 328 xuống 62 với `bilinear`, còn 90
  với `bicubic`. Vì vậy khâu phóng dùng `bicubic`, khâu thu nhỏ dùng `area`.
- **`fgr` mà RVM trả về gần như không làm mềm ảnh** (188.6 so với 193.7 của ảnh gốc
  trong vùng chủ thể) — dùng nó để ghép cho biên sạch là đáng.
- **VAAPI ghi hình chạy trên `/dev/dri/renderD*` thuộc card AMD** — số hiệu node
  không cố định, `recorder.py` dò theo `vendor == 0x1002`.

## Xử lý sự cố

**Hình rất tối.** Camera UVC lưu thông số phơi sáng ngay trên thiết bị, và chế độ
thủ công do bất kỳ chương trình nào đặt sẽ còn nguyên sau khi khởi động lại máy.
Mở mục **Camera (phần cứng)** rồi bật lại **Phơi sáng tự động**, hoặc bấm
**Đặt lại mặc định camera**.

**Meet / OBS không thấy webcam ảo.** Chạy `./run.sh --list-devices` — nó đánh dấu
thiết bị nào thực sự nhận được luồng ghi vào. Thiết bị tạo với `exclusive_caps=1`
có thể khai báo không có cả CAPTURE lẫn OUTPUT, lúc đó không ứng dụng nào ghi vào
được, kể cả ffmpeg. `scripts/setup_v4l2loopback.sh` xử lý chuyện này, gộp luôn
thiết bị của các ứng dụng khác, và ghi thử một khung hình thật rồi mới báo thành công.

**Bám khung bị mờ.** Cắt rồi phóng to phá chất lượng mạnh nhất trong pipeline.
Hãy đặt độ phân giải nguồn cao hơn mức xuất (nguồn 1080p, xuất 720p) để khung cắt
còn đủ điểm ảnh thật.

**`--check` báo thiết bị CPU.** ROCm chưa thấy card. Kiểm tra `rocminfo` có liệt kê
GPU không, và bạn đã ở trong nhóm `render` chưa.

## Đóng góp

Xem [CONTRIBUTING.md](CONTRIBUTING.md). Lưu ý hai điều dễ quên: thêm trường vào
`AppConfig` thì phải thêm một dòng vào `CASES` trong `tests/test_config_wiring.py`,
và mọi chuỗi hiển thị cho người dùng đều viết bằng tiếng Việt.

## Bản quyền

Mã nguồn: MIT — xem [LICENSE](LICENSE). Model RobustVideoMatting theo giấy phép
GPL-3.0 của dự án gốc; YuNet theo giấy phép của OpenCV Zoo. Cả hai được tải lúc
cài đặt, không kèm trong repo — chi tiết ở [NOTICE](NOTICE).

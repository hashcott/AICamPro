#!/usr/bin/env bash
# Tạo thiết bị webcam ảo cho ProCam.
#
# Hai cái bẫy mà script này phải xử lý:
#   1. `modprobe` trên module ĐÃ nạp sẽ bỏ qua mọi tham số, không báo lỗi.
#      Muốn đổi cấu hình bắt buộc phải gỡ module ra rồi nạp lại.
#   2. modprobe đọc mọi file trong /etc/modprobe.d theo thứ tự abc và file SAU
#      ghi đè file trước. Máy có thể đã có sẵn cấu hình của OBS, Iriun, ProVCam…
#      nên file của ProCam phải sắp xếp sau cùng và phải gộp cả thiết bị của
#      những ứng dụng kia, nếu không sẽ làm hỏng webcam ảo của chúng.
set -euo pipefail

DEVICE_NR="${DEVICE_NR:-42}"
LABEL="${LABEL:-ProCam Virtual Camera}"
# exclusive_caps=0 cho thiết bị của ProCam.
#   Ý tưởng của exclusive_caps=1 là: khai báo OUTPUT khi chưa có nguồn ghi, đổi sang
#   CAPTURE khi đã có. Nhưng trên v4l2loopback 0.12.7 / kernel 6.8 nó khai báo
#   KHÔNG có cả hai (caps=0x05200000) nên không ứng dụng nào ghi vào được.
#   Với =0 thiết bị luôn khai báo cả hai — ProCam ghi được, OBS/Zoom/Meet thấy được.
#   Đặt EXCLUSIVE_CAPS=1 nếu ứng dụng nào đó của bạn đòi hỏi kiểu cũ.
EXCLUSIVE="${EXCLUSIVE_CAPS:-0}"
CONF="/etc/modprobe.d/zz-procam-v4l2loopback.conf"   # tên bắt đầu bằng zz để ghi đè các file khác

die() { echo "✗ $*" >&2; exit 1; }
info() { echo "→ $*"; }

[[ $EUID -eq 0 ]] || die "Cần quyền root:  sudo $0"

# ---------- 0. đảm bảo có module ----------
if ! modinfo v4l2loopback >/dev/null 2>&1; then
  info "cài v4l2loopback-dkms"
  apt-get update -qq
  apt-get install -y v4l2loopback-dkms
fi

# ---------- 1. gom các thiết bị loopback đang có ----------
declare -a NRS=() LABELS=() CAPS=()
for dir in /sys/devices/virtual/video4linux/video*; do
  [[ -e "$dir/name" ]] || continue
  nr="${dir##*/video}"
  [[ "$nr" =~ ^[0-9]+$ ]] || continue
  NRS+=("$nr"); LABELS+=("$(cat "$dir/name")"); CAPS+=("1")
done

if [[ ${#NRS[@]} -gt 0 ]]; then
  info "thiết bị loopback đang có: ${NRS[*]} (${LABELS[*]})"
fi

# thêm ProCam nếu chưa có
already=0
for i in "${!NRS[@]}"; do
  [[ "${NRS[$i]}" == "$DEVICE_NR" ]] && { LABELS[$i]="$LABEL"; CAPS[$i]="$EXCLUSIVE"; already=1; }
done
if [[ $already -eq 0 ]]; then
  NRS+=("$DEVICE_NR"); LABELS+=("$LABEL"); CAPS+=("$EXCLUSIVE")
fi

# ---------- 2. ai đang dùng module ----------
refcount="$(awk '/^v4l2loopback /{print $3}' /proc/modules 2>/dev/null || echo 0)"
if [[ "${refcount:-0}" != "0" ]]; then
  echo "Module v4l2loopback đang được dùng (refcount=$refcount)."
  echo "Hãy tắt webcam ảo trong các ứng dụng đang mở (OBS: Stop Virtual Camera) rồi chạy lại."
  for d in /dev/video*; do
    users="$(fuser "$d" 2>/dev/null || true)"
    [[ -n "$users" ]] && echo "  $d đang bị giữ bởi PID:$users"
  done
  die "không gỡ được module để cấu hình lại"
fi

# ---------- 3. ghi cấu hình gộp ----------
join() { local IFS=","; echo "$*"; }
PARAMS="devices=${#NRS[@]} video_nr=$(join "${NRS[@]}") card_label=\"$(join "${LABELS[@]}")\" exclusive_caps=$(join "${CAPS[@]}")"

rm -f /etc/modprobe.d/procam-v4l2loopback.conf      # file sai từ bản script cũ
cat > "$CONF" <<CONFEOF
# Do ProCam tạo. Gộp toàn bộ thiết bị v4l2loopback của máy vào một chỗ vì
# modprobe chỉ dùng giá trị của file được đọc SAU CÙNG.
options v4l2loopback $PARAMS
CONFEOF
echo "v4l2loopback" > /etc/modules-load.d/zz-procam-v4l2loopback.conf
rm -f /etc/modules-load.d/procam-v4l2loopback.conf

info "cấu hình: $PARAMS"

# ---------- 4. nạp lại module ----------
reload() {
  modprobe -r v4l2loopback 2>/dev/null || true
  sleep 0.3
  # shellcheck disable=SC2086
  modprobe v4l2loopback $1 || return 1
  sleep 0.7
}

verify() {   # kiểm tra thật: khai báo OUTPUT + đặt được định dạng + ghi được một khung
  python3 - "$1" <<'PYEOF'
import fcntl, os, struct, sys

QUERYCAP = (2 << 30) | (104 << 16) | (0x56 << 8) | 0
S_FMT    = (3 << 30) | (208 << 16) | (0x56 << 8) | 5
BUF_TYPE_VIDEO_OUTPUT = 2
RGB24 = sum(b << (8 * i) for i, b in enumerate(b"RGB3"))
W, H = 640, 360

path = sys.argv[1]
try:
    fd = os.open(path, os.O_RDWR)
except OSError as exc:
    print(f"MISSING {exc}")
    raise SystemExit(1)

try:
    buf = bytearray(104)
    fcntl.ioctl(fd, QUERYCAP, buf, True)
    caps, dcaps = struct.unpack_from("<II", buf, 84)
    eff = dcaps if caps & 0x80000000 else caps
    if not eff & 0x00000002:
        print(f"NO_OUTPUT caps=0x{eff:08x}")
        raise SystemExit(2)

    fmt = bytearray(208)
    struct.pack_into("<I", fmt, 0, BUF_TYPE_VIDEO_OUTPUT)
    struct.pack_into("<IIIIII", fmt, 4, W, H, RGB24, 1, W * 3, W * H * 3)
    fcntl.ioctl(fd, S_FMT, fmt, True)
    written = os.write(fd, bytes(W * H * 3))
    if written != W * H * 3:
        print(f"SHORT_WRITE {written}")
        raise SystemExit(3)
    print("OUTPUT")
except OSError as exc:
    print(f"WRITE_FAILED {exc}")
    raise SystemExit(4)
finally:
    os.close(fd)
PYEOF
}

info "nạp lại module"
reload "$PARAMS" || die "modprobe thất bại"

result="$(verify "/dev/video$DEVICE_NR" || true)"
if [[ "$result" != OUTPUT* ]]; then
  alt=$([[ "$EXCLUSIVE" == "0" ]] && echo 1 || echo 0)
  echo "⚠ /dev/video$DEVICE_NR chưa nhận ghi ($result) — thử lại với exclusive_caps=$alt"
  for i in "${!NRS[@]}"; do
    [[ "${NRS[$i]}" == "$DEVICE_NR" ]] && CAPS[$i]="$alt"
  done
  PARAMS="devices=${#NRS[@]} video_nr=$(join "${NRS[@]}") card_label=\"$(join "${LABELS[@]}")\" exclusive_caps=$(join "${CAPS[@]}")"
  sed -i "s|^options v4l2loopback .*|options v4l2loopback $PARAMS|" "$CONF"
  reload "$PARAMS" || die "modprobe thất bại"
  result="$(verify "/dev/video$DEVICE_NR" || true)"
fi

# ---------- 5. kết luận trung thực ----------
echo
if [[ "$result" == OUTPUT* ]]; then
  echo "✓ Webcam ảo sẵn sàng: /dev/video$DEVICE_NR — \"$LABEL\""
  echo "  Cấu hình lưu ở $CONF, thiết bị sẽ tự tạo lại sau khi khởi động máy."
else
  die "Không tạo được webcam ảo dùng được. Trạng thái: $result
   Kiểm tra:  dmesg | tail -20"
fi

echo
echo "Các thiết bị video hiện có:"
for dir in /sys/devices/virtual/video4linux/video*; do
  [[ -e "$dir/name" ]] && echo "  /dev/${dir##*/}  $(cat "$dir/name")"
done

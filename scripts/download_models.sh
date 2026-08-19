#!/usr/bin/env bash
# Tải model tách nền cho Soi.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/models"
mkdir -p "$DIR"

RVM_BASE="https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0"

# mặc định: chỉ tải bản mobilenetv3 (đủ dùng thời gian thực).
# truyền "all" để tải thêm resnet50 (chất lượng biên tóc tốt hơn).
MODELS=("rvm_mobilenetv3_fp32.torchscript" "rvm_mobilenetv3_fp16.torchscript")
if [[ "${1:-}" == "all" ]]; then
  MODELS+=("rvm_resnet50_fp32.torchscript" "rvm_resnet50_fp16.torchscript")
fi

for m in "${MODELS[@]}"; do
  if [[ -s "$DIR/$m" ]]; then
    echo "✓ đã có: $m"
    continue
  fi
  echo "↓ tải $m ..."
  curl -fL --retry 3 --progress-bar -o "$DIR/$m.part" "$RVM_BASE/$m"
  mv "$DIR/$m.part" "$DIR/$m"
done

# YuNet: bộ dò khuôn mặt nhẹ, dùng cho auto-framing khi tắt tách nền
YUNET="$DIR/face_detection_yunet_2023mar.onnx"
if [[ ! -s "$YUNET" ]]; then
  echo "↓ tải face_detection_yunet_2023mar.onnx ..."
  curl -fL --retry 3 --progress-bar -o "$YUNET.part" \
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" \
    && mv "$YUNET.part" "$YUNET" || { rm -f "$YUNET.part"; echo "⚠ bỏ qua YuNet (sẽ dùng Haar cascade thay thế)"; }
fi

echo
ls -lh "$DIR" | tail -n +2

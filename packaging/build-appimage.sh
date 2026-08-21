#!/usr/bin/env bash
# Dựng AppImage cho AICamPro.
#
# Nội dung (Python độc lập + Qt + OpenCV + ứng dụng, không có PyTorch) do
# lib-payload.sh dựng, dùng chung với bản tar.gz. File này chỉ gọi appimagetool.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=packaging/lib-payload.sh
source "$ROOT/packaging/lib-payload.sh"

OUT="${OUT_DIR:-$ROOT/dist}"
VERSION="$(payload_version)"
ARCH="$(payload_arch "${ARCH:-}")"
NATIVE="$(payload_arch)"
# Cây này được dựng bằng chính Python đi kèm (pip phải chạy được), nên không
# cross-build được: mỗi kiến trúc cần một runner của chính nó.
[[ "$ARCH" == "$NATIVE" ]] || {
    echo "✗ không cross-build được: yêu cầu $ARCH nhưng máy là $NATIVE" >&2
    exit 1
}

TOOL="appimagetool-${ARCH}.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/${TOOL}"

mkdir -p "$PAYLOAD_CACHE" "$OUT"
APPDIR="$(mktemp -d)/AICamPro.AppDir"
trap 'rm -rf "$(dirname "$APPDIR")"' EXIT

echo "→ tải appimagetool"
payload_fetch "$TOOL_URL" "$PAYLOAD_CACHE/$TOOL"
chmod +x "$PAYLOAD_CACHE/$TOOL"

payload_build "$APPDIR" "$ARCH"

IMAGE="$OUT/AICamPro-${VERSION}-${ARCH}.AppImage"
echo "→ đóng gói AppImage ($(du -sh "$APPDIR" | cut -f1) chưa nén)"
export ARCH          # appimagetool đọc biến này để đặt tên kiến trúc
"$PAYLOAD_CACHE/$TOOL" --appimage-extract-and-run --no-appstream \
    "$APPDIR" "$IMAGE" 2>&1 | tail -3

chmod +x "$IMAGE"
echo "✓ $IMAGE ($(du -h "$IMAGE" | cut -f1))"

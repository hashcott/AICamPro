#!/usr/bin/env bash
# Dựng bản tar.gz chạy tại chỗ cho AICamPro.
#
# Cùng nội dung với AppImage (lib-payload.sh), khác ở chỗ không cần FUSE và
# không cần quyền gì: giải nén ra rồi chạy ./AICamPro. Dành cho máy không cho
# mount AppImage (một số container, một số bản kernel bị khoá user namespace)
# và cho ai muốn xem thẳng nội dung gói.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=packaging/lib-payload.sh
source "$ROOT/packaging/lib-payload.sh"

OUT="${OUT_DIR:-$ROOT/dist}"
VERSION="$(payload_version)"
ARCH="$(payload_arch "${ARCH:-}")"
NATIVE="$(payload_arch)"
[[ "$ARCH" == "$NATIVE" ]] || {
    echo "✗ không cross-build được: yêu cầu $ARCH nhưng máy là $NATIVE" >&2
    exit 1
}

NAME="AICamPro-${VERSION}-${ARCH}"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
mkdir -p "$OUT"

payload_build "$BUILD/$NAME" "$ARCH"

# AppRun định vị mọi thứ tương đối theo `readlink -f "$0"`, nên một symlink tên
# dễ đọc là đủ — không cần thêm một lớp script nữa.
ln -s AppRun "$BUILD/$NAME/AICamPro"
install -m 0644 "$ROOT/LICENSE" "$BUILD/$NAME/LICENSE"
install -m 0644 "$ROOT/README.md" "$BUILD/$NAME/README.md"
install -m 0644 "$ROOT/README.vi.md" "$BUILD/$NAME/README.vi.md"

TARBALL="$OUT/${NAME}.tar.gz"
echo "→ nén ($(du -sh "$BUILD/$NAME" | cut -f1) chưa nén)"
# --owner/--group: file trong gói thuộc root:root bất kể ai build, để giải nén
# bằng sudo vào /opt không mang theo uid của máy build.
tar -czf "$TARBALL" -C "$BUILD" \
    --owner=0 --group=0 --numeric-owner "$NAME"
echo "✓ $TARBALL ($(du -h "$TARBALL" | cut -f1))"
echo "  giải nén rồi chạy: tar -xzf $(basename "$TARBALL") && ./$NAME/AICamPro --setup"

#!/usr/bin/env bash
# Dựng gói Arch Linux (.pkg.tar.zst) cho AICamPro.
#
# Gói là arch=('any') vì toàn bộ mã là Python thuần; phần nhị phân nặng
# (PyTorch ROCm, Qt, OpenCV) do aicampro-setup tải về môi trường người dùng.
#
# PKGBUILD sinh ra ở đây cố tình có source=() rỗng: nó đóng gói cây làm việc
# hiện tại, giống hệt build-deb.sh và build-rpm.sh, chứ không tải lại tarball từ
# GitHub. Nhờ vậy build thử một thay đổi chưa commit cũng ra đúng gói đó, và
# không có checksum nào phải cập nhật bằng tay.
#
# Cần makepkg (gói base-devel). Trên máy không có: chạy trong container Arch —
#   docker run --rm -v "$PWD:/src" -w /src archlinux:base-devel \
#       ./packaging/build-arch.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=packaging/lib-systree.sh
source "$ROOT/packaging/lib-systree.sh"

OUT="${OUT_DIR:-$ROOT/dist}"
VERSION="$(systree_version)"
PKG="aicampro"
RELEASE="${PKGREL:-1}"

command -v makepkg >/dev/null || {
    echo "✗ không có makepkg (Arch: pacman -S base-devel)" >&2
    exit 1
}

BUILD="$(mktemp -d)"
chmod 0755 "$BUILD"      # người dùng build (không phải root) phải đọc được
trap 'rm -rf "$BUILD"' EXIT

# Chỉ chép những gì lib-systree.sh cần — không kéo theo dist/, .git/, model đã tải.
echo "→ chép cây nguồn"
install -d "$BUILD/tree"
cp -r "$ROOT/aicampro" "$ROOT/packaging" "$ROOT/scripts" "$BUILD/tree/"
cp "$ROOT/pyproject.toml" "$ROOT/README.md" "$ROOT/README.vi.md" \
   "$ROOT/CHANGELOG.md" "$ROOT/LICENSE" "$BUILD/tree/"
find "$BUILD/tree" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

cat > "$BUILD/PKGBUILD" <<PKGBUILD
# Maintainer: Harry Nguyen <duchanhstyle@gmail.com>
pkgname=$PKG
pkgver=$VERSION
pkgrel=$RELEASE
pkgdesc="AI webcam with background removal, accelerated on AMD GPUs"
arch=('any')
url="https://github.com/hashcott/AICamPro"
license=('MIT')
depends=('python' 'python-pip' 'ca-certificates' 'curl' 'hicolor-icon-theme')
optdepends=('ffmpeg: ghi hình'
            'v4l2loopback-dkms: webcam ảo cho Meet/Zoom/OBS'
            'zenity: thông báo khi thiếu môi trường chạy')
source=()
options=('!strip')

package() {
    # Cùng một hàm dựng cây /usr với .deb và .rpm — xem packaging/lib-systree.sh.
    # shellcheck source=/dev/null
    source "\$startdir/tree/packaging/lib-systree.sh"
    systree_build "\$pkgdir"
    install -Dm644 "\$startdir/tree/LICENSE" \\
            "\$pkgdir/usr/share/licenses/\$pkgname/LICENSE"
}
PKGBUILD

echo "→ makepkg"
if [[ "$(id -u)" -eq 0 ]]; then
    # makepkg từ chối chạy dưới root. Trong container (CI) đó là trường hợp
    # thường gặp, nên tạo một người dùng dùng-một-lần với HOME nằm trong thư mục
    # build; runuser có sẵn trong util-linux nên không phải cài sudo.
    id -u aicampro-build >/dev/null 2>&1 || \
        useradd --system --no-create-home --home-dir "$BUILD" --shell /bin/bash aicampro-build
    chown -R aicampro-build "$BUILD"
    runuser -u aicampro-build -- env HOME="$BUILD" \
        sh -c "cd '$BUILD' && makepkg --nodeps --noconfirm --force"
else
    ( cd "$BUILD" && makepkg --nodeps --noconfirm --force )
fi

mkdir -p "$OUT"
PACKAGE="$(find "$BUILD" -maxdepth 1 -name "*.pkg.tar.*" -type f | head -1)"
[[ -n "$PACKAGE" ]] || { echo "✗ makepkg không tạo ra gói nào" >&2; exit 1; }
install -m 0644 "$PACKAGE" "$OUT/"
echo "✓ $OUT/$(basename "$PACKAGE") ($(du -h "$PACKAGE" | cut -f1))"

if command -v namcap >/dev/null 2>&1; then
    echo "→ namcap"
    namcap "$OUT/$(basename "$PACKAGE")" || true
fi

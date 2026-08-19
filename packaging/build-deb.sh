#!/usr/bin/env bash
# Dựng gói .deb cho AICamPro.
#
# Gói là Architecture: all — toàn bộ mã là Python thuần, phần nhị phân nặng
# (PyTorch ROCm, Qt, OpenCV) do aicampro-setup tải về môi trường người dùng.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT_DIR:-$ROOT/dist}"
VERSION="$(python3 -c "import tomllib,sys; print(tomllib.load(open('$ROOT/pyproject.toml','rb'))['project']['version'])")"
PKG="aicampro"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

DEST="$BUILD/$PKG"
install -d "$DEST/DEBIAN" \
           "$DEST/usr/bin" \
           "$DEST/usr/lib/$PKG" \
           "$DEST/usr/lib/$PKG/scripts" \
           "$DEST/usr/share/applications" \
           "$DEST/usr/share/icons/hicolor/scalable/apps" \
           "$DEST/usr/share/doc/$PKG" \
           "$DEST/usr/share/man/man1"

echo "→ chép ứng dụng"
cp -r "$ROOT/aicampro" "$DEST/usr/lib/$PKG/"
find "$DEST/usr/lib/$PKG" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
# cp giữ nguyên quyền 664 của cây làm việc; Debian đòi 644 cho file thường
# cp giữ nguyên quyền của cây làm việc (664/775); Debian đòi 644/755
find "$DEST/usr/lib/$PKG" -type f -exec chmod 0644 {} +
find "$DEST/usr/lib/$PKG" -type d -exec chmod 0755 {} +
install -m 0755 "$ROOT/scripts/download_models.sh" "$DEST/usr/lib/$PKG/scripts/"
install -m 0755 "$ROOT/scripts/setup_v4l2loopback.sh" "$DEST/usr/lib/$PKG/scripts/"

echo "→ lệnh và tích hợp desktop"
install -m 0755 "$ROOT/packaging/launcher.sh" "$DEST/usr/bin/aicampro"
install -m 0755 "$ROOT/packaging/aicampro-setup" "$DEST/usr/bin/aicampro-setup"
install -m 0644 "$ROOT/packaging/aicampro.desktop" "$DEST/usr/share/applications/"
for page in aicampro aicampro-setup; do
    gzip -9n -c "$ROOT/packaging/man/$page.1" > "$DEST/usr/share/man/man1/$page.1.gz"
    chmod 0644 "$DEST/usr/share/man/man1/$page.1.gz"
done
install -m 0644 "$ROOT/packaging/icons/aicampro.svg" \
        "$DEST/usr/share/icons/hicolor/scalable/apps/aicampro.svg"
for size in 16 24 32 48 64 128 256 512; do
    install -d "$DEST/usr/share/icons/hicolor/${size}x${size}/apps"
    install -m 0644 "$ROOT/packaging/icons/aicampro-${size}.png" \
            "$DEST/usr/share/icons/hicolor/${size}x${size}/apps/aicampro.png"
done

echo "→ tài liệu"
install -m 0644 "$ROOT/README.md" "$DEST/usr/share/doc/$PKG/"
install -m 0644 "$ROOT/README.vi.md" "$DEST/usr/share/doc/$PKG/"

# Phiên bản không có revision nên dpkg coi đây là gói native: changelog.gz phải
# đúng định dạng Debian, không thể đưa thẳng CHANGELOG.md vào.
DEB_DATE="$(date -R)"
{
    printf '%s (%s) unstable; urgency=medium\n\n' "$PKG" "$VERSION"
    python3 - "$ROOT/CHANGELOG.md" "$VERSION" <<'PYEOF'
import re, sys
from pathlib import Path
text, version = Path(sys.argv[1]).read_text(), sys.argv[2]
m = re.search(rf"^## \[{re.escape(version)}\].*?$\n(.*?)(?=^## \[|\Z)",
              text, re.MULTILINE | re.DOTALL)
body = m.group(1) if m else ""
import textwrap
bullets, current, section = [], None, None
for raw in body.splitlines():
    line = raw.strip()
    if line.startswith("### "):
        section = line[4:]
    elif line.startswith("- "):
        current = line[2:]
        bullets.append((section, current))
    elif line and bullets and not line.startswith("#"):
        bullets[-1] = (bullets[-1][0], bullets[-1][1] + " " + line)
last = None
for section, text in bullets:
    if section != last:
        print(f"  * {section}:")
        last = section
    for i, chunk in enumerate(textwrap.wrap(text, 68)):
        print(("    - " if i == 0 else "      ") + chunk)
if not bullets:
    print("  * Initial release.")
PYEOF
    printf '\n -- Harry Nguyen <duchanhstyle@gmail.com>  %s\n' "$DEB_DATE"
} | gzip -9n > "$DEST/usr/share/doc/$PKG/changelog.gz"
chmod 0644 "$DEST/usr/share/doc/$PKG/changelog.gz"
{
    echo "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/"
    echo "Upstream-Name: AICamPro"
    echo "Source: https://github.com/hashcott/AICamPro"
    echo
    echo "Files: *"
    echo "Copyright: 2026 Harry Nguyen"
    echo "License: MIT"
    sed 's/^$/./; s/^/ /' "$ROOT/LICENSE"
} > "$DEST/usr/share/doc/$PKG/copyright"
chmod 0644 "$DEST/usr/share/doc/$PKG/copyright"

INSTALLED_KB="$(du -ks "$DEST" | cut -f1)"
cat > "$DEST/DEBIAN/control" <<CONTROL
Package: $PKG
Version: $VERSION
Section: video
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-venv, ca-certificates, curl
Recommends: ffmpeg, v4l2loopback-dkms
Suggests: zenity
Maintainer: Harry Nguyen <duchanhstyle@gmail.com>
Homepage: https://github.com/hashcott/AICamPro
Installed-Size: $INSTALLED_KB
Description: AI webcam with background removal, accelerated on AMD GPUs
 AICamPro removes, blurs or replaces your webcam background, grades colour,
 retouches and auto-frames you, then offers the result to Meet, Zoom, Discord
 or OBS as a virtual camera. Every per-frame operation runs on the GPU through
 PyTorch on ROCm.
 .
 This package contains the application only. The GPU runtime — PyTorch built
 for ROCm — is around 14 GB installed and has to match the amdgpu driver on
 the machine, so it is fetched into a per-user environment by running
 aicampro-setup once after installation.
CONTROL

cat > "$DEST/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    cat <<'MSG'

AICamPro đã cài. Chạy một lần để tải môi trường GPU và model:

    aicampro-setup

Muốn dùng webcam ảo trong Meet/Zoom/OBS thì chạy thêm:

    sudo /usr/lib/aicampro/scripts/setup_v4l2loopback.sh

MSG
fi
POSTINST
chmod 0755 "$DEST/DEBIAN/postinst"

echo "→ md5sums"
( cd "$DEST" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' \
    | sort -z | xargs -0 md5sum > DEBIAN/md5sums )
chmod 0644 "$DEST/DEBIAN/md5sums"

echo "→ đóng gói"
mkdir -p "$OUT"
DEB="$OUT/${PKG}_${VERSION}_all.deb"
# --root-owner-group đặt chủ sở hữu root:root mà không cần fakeroot, nên máy
# build không phải cài thêm gói nào ngoài dpkg.
dpkg-deb --root-owner-group --build -Zxz "$DEST" "$DEB" >/dev/null
echo "✓ $DEB ($(du -h "$DEB" | cut -f1))"

if command -v lintian >/dev/null 2>&1; then
    echo "→ lintian"
    lintian --no-tag-display-limit "$DEB" || true
fi

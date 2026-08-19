#!/usr/bin/env bash
# Dựng AppImage cho AICamPro.
#
# Bên trong có: Python độc lập, Qt (PySide6-Essentials), OpenCV, numpy,
# pyvirtualcam và bản thân ứng dụng. KHÔNG có PyTorch — bản ROCm chiếm 14 GB
# sau khi cài và phải khớp driver amdgpu, nên nó được tải một lần vào môi
# trường riêng của người dùng, tạo bằng chính Python trong AppImage để khớp ABI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT_DIR:-$ROOT/dist}"
CACHE="${APPIMAGE_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/aicampro-build}"
VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('$ROOT/pyproject.toml','rb'))['project']['version'])")"
PY_VERSION="${PY_VERSION:-3.12.14}"
PY_RELEASE="${PY_RELEASE:-20260814}"
ARCH="x86_64"

PY_TARBALL="cpython-${PY_VERSION}+${PY_RELEASE}-${ARCH}-unknown-linux-gnu-install_only.tar.gz"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_RELEASE}/${PY_TARBALL}"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"

mkdir -p "$CACHE" "$OUT"
APPDIR="$(mktemp -d)/AICamPro.AppDir"
trap 'rm -rf "$(dirname "$APPDIR")"' EXIT

fetch() {  # url dest
    [[ -s "$2" ]] && { echo "  ✓ đã có $(basename "$2")"; return; }
    echo "  ↓ $(basename "$2")"
    curl -fL --retry 3 --progress-bar -o "$2.part" "$1"
    mv "$2.part" "$2"
}

echo "→ tải công cụ"
fetch "$PY_URL" "$CACHE/$PY_TARBALL"
fetch "$TOOL_URL" "$CACHE/appimagetool"
chmod +x "$CACHE/appimagetool"

echo "→ dựng AppDir"
install -d "$APPDIR/usr/lib/aicampro" "$APPDIR/usr/share/applications" \
           "$APPDIR/usr/share/icons/hicolor/scalable/apps" "$APPDIR/usr/bin"
tar -xzf "$CACHE/$PY_TARBALL" -C "$APPDIR/usr"
mv "$APPDIR/usr/python" "$APPDIR/usr/pyruntime"
APP_PY="$APPDIR/usr/pyruntime/bin/python3"

echo "→ cài phụ thuộc chạy nền (không có torch)"
"$APP_PY" -m pip install --quiet --no-cache-dir --upgrade pip
"$APP_PY" -m pip install --quiet --no-cache-dir \
    "PySide6-Essentials>=6.6" "opencv-python-headless>=4.9" \
    "numpy>=1.26" "pyvirtualcam>=0.11"

echo "→ cắt bớt phần không dùng"
SITE="$(find "$APPDIR/usr/pyruntime/lib" -maxdepth 2 -name site-packages -type d | head -1)"
rm -rf "$APPDIR/usr/pyruntime/lib/python"*/test \
       "$APPDIR/usr/pyruntime/lib/python"*/idlelib \
       "$APPDIR/usr/pyruntime/lib/python"*/tkinter \
       "$SITE/pip" "$SITE/setuptools" "$SITE"/*.dist-info/RECORD
find "$APPDIR/usr/pyruntime" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$APPDIR/usr/pyruntime" -name '*.pyc' -delete 2>/dev/null || true
# Qt kéo theo cả bản dịch và ví dụ, không cần cho bản phát hành
rm -rf "$SITE/PySide6/Qt/translations" "$SITE/PySide6/examples" "$SITE/PySide6/glue" \
       "$SITE/PySide6/Qt/qml" "$SITE/PySide6/Qt/plugins/qmltooling" 2>/dev/null || true

echo "→ chép ứng dụng"
cp -r "$ROOT/aicampro" "$APPDIR/usr/lib/aicampro/"
find "$APPDIR/usr/lib/aicampro" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
install -m 0755 "$ROOT/packaging/aicampro-setup" "$APPDIR/usr/bin/aicampro-setup"
install -m 0755 "$ROOT/scripts/download_models.sh" "$APPDIR/usr/bin/download_models.sh"
install -m 0755 "$ROOT/scripts/setup_v4l2loopback.sh" "$APPDIR/usr/bin/setup_v4l2loopback.sh"
install -m 0644 "$ROOT/packaging/aicampro.desktop" "$APPDIR/usr/share/applications/"
install -m 0644 "$ROOT/packaging/aicampro.desktop" "$APPDIR/aicampro.desktop"
install -m 0644 "$ROOT/packaging/icons/aicampro.svg" \
        "$APPDIR/usr/share/icons/hicolor/scalable/apps/aicampro.svg"
install -m 0644 "$ROOT/packaging/icons/aicampro-256.png" "$APPDIR/aicampro.png"
install -m 0644 "$ROOT/LICENSE" "$APPDIR/usr/lib/aicampro/LICENSE"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
set -eu
HERE="$(dirname "$(readlink -f "$0")")"
PY="$HERE/usr/pyruntime/bin/python3"
APP_DIR="$HERE/usr/lib/aicampro"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/aicampro"
RUNTIME="$DATA_DIR/runtime"

export AICAMPRO_MODEL_DIR="${AICAMPRO_MODEL_DIR:-$DATA_DIR/models}"
export AICAMPRO_BOOTSTRAP_PYTHON="$PY"
export AICAMPRO_SCRIPTS="$HERE/usr/bin"
export PATH="$HERE/usr/bin:$PATH"

# PyTorch được cài thẳng vào một thư mục (không venv): Python của AppImage nằm
# ở điểm mount tạm, đổi mỗi lần chạy, nên venv trỏ vào đó hỏng ngay khi thoát.
if [ -d "$RUNTIME" ]; then
    export PYTHONPATH="$RUNTIME${PYTHONPATH:+:$PYTHONPATH}"
fi

case "${1:-}" in
    --setup)   exec "$HERE/usr/bin/aicampro-setup" --minimal ;;
    --shell)   shift; exec "$PY" "$@" ;;
esac

if ! "$PY" -c 'import torch' >/dev/null 2>&1; then
    msg="AICamPro chưa có phần chạy trên GPU.

PyTorch bản ROCm nặng 14 GB và phải khớp driver amdgpu nên không nằm trong
AppImage. Chạy một lần:

    $(readlink -f "$0") --setup"
    if [ -t 0 ]; then
        printf '%s\n\n' "$msg" >&2
        printf 'Chạy ngay bây giờ? [Y/n] ' >&2
        read -r a || a=n
        case "$a" in [Nn]*) exit 1 ;; *) exec "$HERE/usr/bin/aicampro-setup" --minimal ;; esac
    elif [ -t 2 ]; then
        printf '%s\n' "$msg" >&2
        exit 1
    fi
    if command -v x-terminal-emulator >/dev/null 2>&1; then
        exec x-terminal-emulator -e "$0" --setup
    elif command -v zenity >/dev/null 2>&1; then
        zenity --error --no-wrap --title=AICamPro --text="$msg"
    else
        printf '%s\n' "$msg" >&2
    fi
    exit 1
fi

exec "$PY" -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); \
from aicampro.__main__ import main; sys.exit(main())' "$APP_DIR" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

echo "→ đóng gói AppImage ($(du -sh "$APPDIR" | cut -f1) chưa nén)"
export ARCH          # appimagetool đọc biến này để đặt tên kiến trúc
"$CACHE/appimagetool" --appimage-extract-and-run --no-appstream \
    "$APPDIR" "$OUT/AICamPro-${VERSION}-${ARCH}.AppImage" 2>&1 | tail -3

chmod +x "$OUT/AICamPro-${VERSION}-${ARCH}.AppImage"
echo "✓ $OUT/AICamPro-${VERSION}-${ARCH}.AppImage ($(du -h "$OUT/AICamPro-${VERSION}-${ARCH}.AppImage" | cut -f1))"

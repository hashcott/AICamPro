# shellcheck shell=bash
# Cây "mang theo tất cả" dùng chung cho AppImage và bản tar.gz chạy tại chỗ.
#
# Bên trong có: Python độc lập, Qt (PySide6-Essentials), OpenCV, numpy,
# pyvirtualcam và bản thân ứng dụng. KHÔNG có PyTorch — bản ROCm chiếm 14 GB
# sau khi cài và phải khớp driver amdgpu, nên nó được tải một lần vào môi
# trường riêng của người dùng, tạo bằng chính Python trong cây này để khớp ABI.
#
# AppImage và tar.gz khác nhau đúng một bước cuối (appimagetool so với tar), nên
# toàn bộ phần dựng cây nằm ở đây. Kịch bản khởi chạy (AppRun) cũng dùng chung:
# nó định vị mọi thứ tương đối theo `readlink -f "$0"`, đúng cả khi nằm trong
# điểm mount tạm của AppImage lẫn khi được giải nén ra một thư mục thật.
#
# Cách dùng:
#   source "$(dirname "$0")/lib-payload.sh"
#   payload_build /đường/dẫn/AppDir x86_64

PAYLOAD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAYLOAD_CACHE="${APPIMAGE_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/aicampro-build}"
PY_VERSION="${PY_VERSION:-3.12.14}"
PY_RELEASE="${PY_RELEASE:-20260814}"

payload_version() {
    python3 -c "import tomllib; print(tomllib.load(open('$PAYLOAD_ROOT/pyproject.toml','rb'))['project']['version'])"
}

# Chuẩn hoá tên kiến trúc. python-build-standalone và appimagetool dùng cùng
# cách gọi (x86_64 / aarch64), nên một tên là đủ cho cả hai.
payload_arch() {  # [uname -m]
    local raw="${1:-$(uname -m)}"
    case "$raw" in
        x86_64 | amd64) echo x86_64 ;;
        aarch64 | arm64) echo aarch64 ;;
        *) echo "✗ kiến trúc không hỗ trợ: $raw" >&2; return 1 ;;
    esac
}

payload_fetch() {  # url dest
    [[ -s "$2" ]] && { echo "  ✓ đã có $(basename "$2")"; return; }
    echo "  ↓ $(basename "$2")"
    curl -fL --retry 3 --progress-bar -o "$2.part" "$1"
    mv "$2.part" "$2"
}

# Dựng cây hoàn chỉnh vào $1 cho kiến trúc $2. Không ghi gì ngoài $1 và cache.
payload_build() {  # dest_dir arch
    local dest="$1" arch="$2"
    local tarball="cpython-${PY_VERSION}+${PY_RELEASE}-${arch}-unknown-linux-gnu-install_only.tar.gz"
    local url="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_RELEASE}/${tarball}"

    mkdir -p "$PAYLOAD_CACHE"
    echo "→ tải Python độc lập ($arch)"
    payload_fetch "$url" "$PAYLOAD_CACHE/$tarball"

    echo "→ dựng cây"
    install -d "$dest/usr/lib/aicampro" "$dest/usr/share/applications" \
               "$dest/usr/share/icons/hicolor/scalable/apps" "$dest/usr/bin"
    tar -xzf "$PAYLOAD_CACHE/$tarball" -C "$dest/usr"
    mv "$dest/usr/python" "$dest/usr/pyruntime"
    local app_py="$dest/usr/pyruntime/bin/python3"

    echo "→ cài phụ thuộc chạy nền (không có torch)"
    "$app_py" -m pip install --quiet --no-cache-dir --upgrade pip
    "$app_py" -m pip install --quiet --no-cache-dir \
        "PySide6-Essentials>=6.6" "opencv-python-headless>=4.9" \
        "numpy>=1.26" "pyvirtualcam>=0.11"

    echo "→ cắt bớt phần không dùng"
    local site
    site="$(find "$dest/usr/pyruntime/lib" -maxdepth 2 -name site-packages -type d | head -1)"
    rm -rf "$dest/usr/pyruntime/lib/python"*/test \
           "$dest/usr/pyruntime/lib/python"*/idlelib \
           "$dest/usr/pyruntime/lib/python"*/tkinter \
           "$site/pip" "$site/setuptools" "$site"/*.dist-info/RECORD
    find "$dest/usr/pyruntime" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    find "$dest/usr/pyruntime" -name '*.pyc' -delete 2>/dev/null || true
    # Qt kéo theo cả bản dịch và ví dụ, không cần cho bản phát hành
    rm -rf "$site/PySide6/Qt/translations" "$site/PySide6/examples" "$site/PySide6/glue" \
           "$site/PySide6/Qt/qml" "$site/PySide6/Qt/plugins/qmltooling" 2>/dev/null || true

    echo "→ chép ứng dụng"
    cp -r "$PAYLOAD_ROOT/aicampro" "$dest/usr/lib/aicampro/"
    find "$dest/usr/lib/aicampro" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    install -m 0755 "$PAYLOAD_ROOT/packaging/aicampro-setup" "$dest/usr/bin/aicampro-setup"
    install -m 0755 "$PAYLOAD_ROOT/scripts/download_models.sh" "$dest/usr/bin/download_models.sh"
    install -m 0755 "$PAYLOAD_ROOT/scripts/setup_v4l2loopback.sh" "$dest/usr/bin/setup_v4l2loopback.sh"
    install -m 0644 "$PAYLOAD_ROOT/packaging/aicampro.desktop" "$dest/usr/share/applications/"
    install -m 0644 "$PAYLOAD_ROOT/packaging/aicampro.desktop" "$dest/aicampro.desktop"
    install -m 0644 "$PAYLOAD_ROOT/packaging/icons/aicampro.svg" \
            "$dest/usr/share/icons/hicolor/scalable/apps/aicampro.svg"
    install -m 0644 "$PAYLOAD_ROOT/packaging/icons/aicampro-256.png" "$dest/aicampro.png"
    install -m 0644 "$PAYLOAD_ROOT/LICENSE" "$dest/usr/lib/aicampro/LICENSE"
    install -m 0644 "$PAYLOAD_ROOT/README.md" "$dest/usr/lib/aicampro/README.md"
    install -m 0644 "$PAYLOAD_ROOT/README.vi.md" "$dest/usr/lib/aicampro/README.vi.md"

    cat > "$dest/AppRun" <<'APPRUN'
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

# PyTorch được cài thẳng vào một thư mục (không venv): Python đi kèm có thể nằm
# ở điểm mount tạm của AppImage, đổi mỗi lần chạy, nên venv trỏ vào đó hỏng ngay
# khi ứng dụng thoát.
if [ -d "$RUNTIME" ]; then
    export PYTHONPATH="$RUNTIME${PYTHONPATH:+:$PYTHONPATH}"
fi

case "${1:-}" in
    --setup)   exec "$HERE/usr/bin/aicampro-setup" --minimal ;;
    --shell)   shift; exec "$PY" "$@" ;;
esac

if ! "$PY" -c 'import torch' >/dev/null 2>&1; then
    msg="AICamPro chưa có phần chạy trên GPU.

PyTorch bản ROCm nặng 14 GB và phải khớp driver amdgpu nên không nằm trong gói.
Chạy một lần:

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
    chmod +x "$dest/AppRun"
}

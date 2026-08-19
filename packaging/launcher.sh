#!/bin/sh
# Bộ khởi chạy AICamPro cho bản đã cài (.deb).
#
# Ứng dụng nằm ở /usr/lib/aicampro, còn phần chạy nặng (PyTorch ROCm, Qt) nằm
# trong môi trường riêng của người dùng vì nó tới 14 GB và phải khớp driver.
set -eu

APP_DIR="${AICAMPRO_APP_DIR:-/usr/lib/aicampro}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/aicampro"
VENV_PYTHON="$DATA_DIR/venv/bin/python"

notify_missing() {
    msg="AICamPro chưa có môi trường chạy.

Chạy lệnh sau một lần để tải PyTorch ROCm và model:

    aicampro-setup"
    # -t 0 : có người đang gõ, hỏi được.
    # -t 2 : có terminal để in ra nhưng đầu vào bị chuyển hướng (script, pipe).
    # không có gì: chạy từ biểu tượng desktop, phải mở terminal hoặc hộp thoại.
    if [ -t 0 ]; then
        printf '%s\n\n' "$msg" >&2
        printf 'Chạy aicampro-setup ngay bây giờ? [Y/n] ' >&2
        read -r answer || answer=n
        case "$answer" in
            [Nn]*) exit 1 ;;
            *) exec aicampro-setup ;;
        esac
    elif [ -t 2 ]; then
        printf '%s\n' "$msg" >&2
        exit 1
    fi
    if command -v x-terminal-emulator >/dev/null 2>&1; then
        exec x-terminal-emulator -e aicampro-setup
    elif command -v zenity >/dev/null 2>&1; then
        zenity --error --no-wrap --title="AICamPro" --text="$msg"
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --error "$msg"
    else
        printf '%s\n' "$msg" >&2
    fi
    exit 1
}

if [ -n "${AICAMPRO_PYTHON:-}" ] && [ -x "${AICAMPRO_PYTHON}" ]; then
    PYTHON="$AICAMPRO_PYTHON"
elif [ -x "$VENV_PYTHON" ]; then
    PYTHON="$VENV_PYTHON"
else
    notify_missing
fi

# Có venv chưa đủ — nó có thể được tạo dở dang rồi bỏ giữa chừng.
if ! "$PYTHON" -c 'import torch, PySide6, cv2, numpy' 2>/dev/null; then
    notify_missing
fi

export AICAMPRO_MODEL_DIR="${AICAMPRO_MODEL_DIR:-$DATA_DIR/models}"

# Không dùng `python -m aicampro`: cả -m lẫn -c đều đặt thư mục hiện tại lên đầu
# sys.path, nên chạy lệnh này từ một thư mục có sẵn ./aicampro/ sẽ nạp nhầm bản
# đó thay vì bản đã cài. Chèn thẳng APP_DIR vào vị trí 0 để chắc chắn.
exec "$PYTHON" -c 'import sys; sys.path.insert(0, sys.argv.pop(1)); from aicampro.__main__ import main; sys.exit(main())' "$APP_DIR" "$@"

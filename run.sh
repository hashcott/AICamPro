#!/usr/bin/env bash
# Khởi chạy AICamPro trong môi trường conda "aicampro".
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_BASE="${CONDA_BASE:-$HOME/miniconda3}"

if [[ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  source "$CONDA_BASE/etc/profile.d/conda.sh"
  conda activate aicampro
else
  echo "⚠ Không tìm thấy conda tại $CONDA_BASE — dùng python hiện hành." >&2
fi

cd "$HERE"
exec python -m aicampro "$@"

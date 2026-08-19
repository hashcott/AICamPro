#!/usr/bin/env bash
# Tạo môi trường conda "procam" với PyTorch ROCm cho GPU AMD.
set -euo pipefail
ENV_NAME="${ENV_NAME:-procam}"
PY_VER="${PY_VER:-3.12}"
ROCM_CHANNEL="${ROCM_CHANNEL:-rocm6.4}"
CONDA_BASE="${CONDA_BASE:-$HOME/miniconda3}"

# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "→ tạo env $ENV_NAME (python $PY_VER)"
  conda create -y -n "$ENV_NAME" "python=$PY_VER"
fi
conda activate "$ENV_NAME"

echo "→ cài PyTorch ROCm ($ROCM_CHANNEL)"
pip install --upgrade torch torchvision \
  --index-url "https://download.pytorch.org/whl/$ROCM_CHANNEL"

echo "→ cài phần còn lại"
pip install --upgrade PySide6 opencv-python-headless numpy pyvirtualcam

echo
python - <<'PY'
import torch
print("torch:", torch.__version__, "| HIP:", torch.version.hip)
print("GPU khả dụng:", torch.cuda.is_available())
if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    print("→", p.name, f"{p.total_memory/1024**3:.1f} GB", getattr(p, "gcnArchName", ""))
else:
    print("⚠ Không thấy GPU. Kiểm tra: người dùng có trong nhóm 'render' và 'video' chưa?")
PY
echo
echo "Xong. Tiếp theo:  ./scripts/download_models.sh  rồi  ./run.sh"

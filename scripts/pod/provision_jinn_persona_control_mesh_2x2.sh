#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/workspace/ConstitutionalAlignment}"
: "${EXPECTED_COMMIT:?Set EXPECTED_COMMIT to the frozen launch commit.}"

mkdir -p /workspace
if [[ ! -d "${REPO_ROOT}/.git" ]]; then
  git clone \
    --branch experiment/moral-control-mesh-v1 \
    --single-branch \
    https://github.com/MoralityLabAI/ConstitutionalAlignment.git \
    "${REPO_ROOT}"
fi
cd "${REPO_ROOT}"
actual_commit="$(git rev-parse HEAD)"
if [[ "${actual_commit}" != "${EXPECTED_COMMIT}" ]]; then
  printf 'Expected commit %s, found %s\n' \
    "${EXPECTED_COMMIT}" "${actual_commit}" >&2
  exit 31
fi

if ! python3 -m pip --version >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3-pip \
    python3-venv
fi

python3 -m pip install --disable-pip-version-check \
  --index-url https://download.pytorch.org/whl/cu124 \
  "torch==2.5.1"
python3 -m pip install --disable-pip-version-check \
  "transformers @ git+https://github.com/huggingface/transformers.git@b6d5084fb4a5dd11e44005a5fa009e7943271090" \
  "jinja2>=3.1,<4" \
  "accelerate>=1.2,<2" \
  "bitsandbytes>=0.45,<1" \
  "datasets>=3.2,<5" \
  "peft>=0.14,<1" \
  "verifiers>=0.2.1,<0.3"
python3 -m pip install --disable-pip-version-check \
  --no-deps -e environments/jinn_beast_metta

python3 - <<'PY'
import peft
import torch
import transformers
from jinn_beast_metta.mesh_v2 import ExogenousMeshController

assert ExogenousMeshController
print(
    {
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "peft": peft.__version__,
        "cuda_available": torch.cuda.is_available(),
    }
)
PY
if nvidia-smi --query-compute-apps=pid --format=csv,noheader | grep -q .; then
  echo "Provisioning left an unexpected GPU compute process." >&2
  exit 32
fi

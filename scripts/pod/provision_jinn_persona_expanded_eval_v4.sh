#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/workspace/ConstitutionalAlignment}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-1a1f53b3ec61e793512bb168ebcedef8d57d26ad}"
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

python3 -m pip install --disable-pip-version-check \
  --index-url https://download.pytorch.org/whl/cu124 \
  "torch==2.5.1"
python3 -m pip install --disable-pip-version-check \
  "transformers @ git+https://github.com/huggingface/transformers.git@b6d5084fb4a5dd11e44005a5fa009e7943271090" \
  "jinja2>=3.1,<4" \
  "accelerate>=1.2,<2" \
  "bitsandbytes>=0.45,<1" \
  "datasets>=3.2,<5" \
  "peft>=0.14,<1"

python3 - <<'PY'
import peft
import torch
import transformers

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

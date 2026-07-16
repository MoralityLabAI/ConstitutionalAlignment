#!/usr/bin/env bash
set -euo pipefail

ENV_PATH="${ENV_PATH:-/home/patrick/.venv-trinity}"
CACHE_DIR="${CACHE_DIR:-/home/patrick/hf_cache}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SMOKE_MODEL_PATH="${SMOKE_MODEL_PATH:-/home/patrick/models/Trinity-Nano-Preview}"
SKIP_SMOKE_TEST="${SKIP_SMOKE_TEST:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SMOKE_SCRIPT="${REPO_ROOT}/scripts/model_env_smoke.py"

echo "==> Trinity env path: ${ENV_PATH}"
echo "==> Cache dir: ${CACHE_DIR}"

mkdir -p "$(dirname "${ENV_PATH}")" "${CACHE_DIR}" "${CACHE_DIR}/triton"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

if [ ! -x "${ENV_PATH}/bin/python" ]; then
  echo "==> Creating venv"
  rm -rf "${ENV_PATH}"
  "${PYTHON_BIN}" -m pip install --user --upgrade --break-system-packages virtualenv
  "${PYTHON_BIN}" -m virtualenv "${ENV_PATH}"
fi

PY="${ENV_PATH}/bin/python"
PIP="${ENV_PATH}/bin/pip"

echo "==> Upgrading pip tooling"
"${PY}" -m pip install --upgrade pip setuptools wheel

echo "==> Installing PyTorch CUDA 12.1 wheels"
"${PIP}" install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo "==> Installing Trinity training dependencies"
"${PIP}" install --upgrade \
  accelerate \
  bitsandbytes \
  datasets \
  jsonschema \
  peft \
  pyyaml \
  sentencepiece \
  trl

echo "==> Installing transformers main branch from archive"
"${PIP}" install --upgrade "https://github.com/huggingface/transformers/archive/refs/heads/main.zip"

ACTIVATE_HELPER="${ENV_PATH}/bin/activate_trinity_env.sh"
cat > "${ACTIVATE_HELPER}" <<EOF
#!/usr/bin/env bash
export HF_HOME="${CACHE_DIR}"
export HUGGINGFACE_HUB_CACHE="\${HF_HOME}"
export TRANSFORMERS_CACHE="\${HF_HOME}"
export TRITON_CACHE_DIR="\${HF_HOME}/triton"
source "${ENV_PATH}/bin/activate"
echo "HF_HOME=\${HF_HOME}"
EOF
chmod +x "${ACTIVATE_HELPER}"

if [ "${SKIP_SMOKE_TEST}" != "1" ]; then
  if [ ! -e "${SMOKE_MODEL_PATH}" ]; then
    echo "Smoke model path not found: ${SMOKE_MODEL_PATH}" >&2
    exit 1
  fi
  echo "==> Running Trinity smoke test"
  export HF_HOME="${CACHE_DIR}"
  export HUGGINGFACE_HUB_CACHE="${HF_HOME}"
  export TRANSFORMERS_CACHE="${HF_HOME}"
  export TRITON_CACHE_DIR="${HF_HOME}/triton"
  "${PY}" "${SMOKE_SCRIPT}" --model-id "${SMOKE_MODEL_PATH}" --cache-dir "${CACHE_DIR}"
fi

echo "==> Trinity environment ready"
echo "Activate with: source ${ACTIVATE_HELPER}"

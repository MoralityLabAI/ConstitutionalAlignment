#!/bin/bash
#SBATCH --nodes=1
#SBATCH --gres=gpu:8
#SBATCH --cpus-per-task=32
#SBATCH --mem=256G
#SBATCH --time=12:00:00
set -euo pipefail

MODEL_DIR="$SILICO_EXPERIMENT_ARTIFACTS_DIR/models/Qwen2.5-72B-Instruct"
PORT=${PORT:-30000}
SGLANG_ROOT="$HOME/.silico/libraries/sglang-fork"

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export SGLANG_DISABLE_CUDNN_CHECK=1
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7

# Home filesystem quota is exceeded; redirect all JIT/compile caches to the
# artifacts volume (4 TB free) so triton/torch can write their kernel caches.
CACHE_ROOT="$SILICO_EXPERIMENT_ARTIFACTS_DIR/cache"
mkdir -p "$CACHE_ROOT/triton" "$CACHE_ROOT/inductor" "$CACHE_ROOT/xdg" "$CACHE_ROOT/hf"
export TRITON_CACHE_DIR="$CACHE_ROOT/triton"
export TORCHINDUCTOR_CACHE_DIR="$CACHE_ROOT/inductor"
export XDG_CACHE_HOME="$CACHE_ROOT/xdg"
export HF_HOME="$CACHE_ROOT/hf"
export SGLANG_CACHE_DIR="$CACHE_ROOT/sglang"

echo "SERVER_NODE $(hostname)"
echo "SERVER_PORT $PORT"

cd "$SGLANG_ROOT/python"
exec uv run python -m sglang.launch_server \
  --model-path "$MODEL_DIR" \
  --served-model-name qwen2.5-72b \
  --tp 8 \
  --host 0.0.0.0 \
  --port "$PORT" \
  --trust-remote-code \
  --log-level info \
  --dtype auto \
  --disable-cuda-graph \
  --mem-fraction-static 0.85 \
  --max-running-requests 96

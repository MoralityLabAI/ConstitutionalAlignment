#!/bin/bash
#SBATCH --nodes=1
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=24
#SBATCH --mem=256G
#SBATCH --time=12:00:00
set -euo pipefail

MODEL_DIR="$SILICO_EXPERIMENT_ARTIFACTS_DIR/models/INTELLECT-3"
PORT=${PORT:-30001}
SGLANG_ROOT="$HOME/.silico/libraries/sglang-fork"

export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
export SGLANG_DISABLE_CUDNN_CHECK=1
export CUDA_VISIBLE_DEVICES=0,1,2,3

# Home filesystem quota is exceeded; redirect all JIT/compile caches to artifacts.
CACHE_ROOT="$SILICO_EXPERIMENT_ARTIFACTS_DIR/cache"
mkdir -p "$CACHE_ROOT/triton" "$CACHE_ROOT/inductor" "$CACHE_ROOT/xdg" "$CACHE_ROOT/hf"
export TRITON_CACHE_DIR="$CACHE_ROOT/triton"
export TORCHINDUCTOR_CACHE_DIR="$CACHE_ROOT/inductor"
export XDG_CACHE_HOME="$CACHE_ROOT/xdg"
export HF_HOME="$CACHE_ROOT/hf"

echo "SERVER_NODE $(hostname)"
echo "SERVER_PORT $PORT"

cd "$SGLANG_ROOT/python"
exec uv run python -m sglang.launch_server \
  --model-path "$MODEL_DIR" \
  --served-model-name intellect-3 \
  --tp 4 \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info \
  --dtype bfloat16 \
  --reasoning-parser glm45 \
  --disable-cuda-graph \
  --mem-fraction-static 0.85 \
  --max-running-requests 96 \
  --context-length 32768

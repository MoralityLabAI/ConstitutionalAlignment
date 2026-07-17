#!/bin/bash
#SBATCH --nodes=1
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=24
#SBATCH --mem=256G
#SBATCH --time=02:00:00
set -euo pipefail
CACHE_ROOT="$SILICO_EXPERIMENT_ARTIFACTS_DIR/cache"
mkdir -p "$CACHE_ROOT/triton" "$CACHE_ROOT/inductor" "$CACHE_ROOT/xdg" "$CACHE_ROOT/hf"
export TRITON_CACHE_DIR="$CACHE_ROOT/triton" TORCHINDUCTOR_CACHE_DIR="$CACHE_ROOT/inductor"
export XDG_CACHE_HOME="$CACHE_ROOT/xdg" HF_HOME="$CACHE_ROOT/hf"
cd ~/.silico/libraries/goodfire-core
uv run python "$SILICO_EXPERIMENT_DIR/src/harvest_activations.py"

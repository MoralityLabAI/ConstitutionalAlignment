#!/bin/bash
#SBATCH --nodes=1
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=24
#SBATCH --mem=256G
#SBATCH --time=03:00:00
set -euo pipefail
cd "$SILICO_EXPERIMENT_DIR"

export SGLANG_DISABLE_CUDNN_CHECK=1
CACHE_ROOT="$SILICO_EXPERIMENT_ARTIFACTS_DIR/cache"
mkdir -p "$CACHE_ROOT/triton" "$CACHE_ROOT/inductor" "$CACHE_ROOT/xdg" "$CACHE_ROOT/hf"
export TRITON_CACHE_DIR="$CACHE_ROOT/triton"
export TORCHINDUCTOR_CACHE_DIR="$CACHE_ROOT/inductor"
export XDG_CACHE_HOME="$CACHE_ROOT/xdg"
export HF_HOME="$CACHE_ROOT/hf"

LOG="$SILICO_EXPERIMENT_ARTIFACTS_DIR/activations/harvest_${SLURM_JOB_ID:-manual}.log"
mkdir -p "$SILICO_EXPERIMENT_ARTIFACTS_DIR/activations"
echo "HARVEST_NODE $(hostname) SMOKE=${HARVEST_SMOKE:-0} $(date -u +%H:%M:%S)" | tee "$LOG"
cd ~/.silico/libraries/goodfire-core
PYTHONPATH="$SILICO_EXPERIMENT_DIR/src" uv run python "$SILICO_EXPERIMENT_DIR/src/harvest_stress.py" 2>&1 | tee -a "$LOG"

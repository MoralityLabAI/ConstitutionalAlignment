#!/bin/bash
# CPU sbatch wrapper: runs an experiment-12 python driver (async HTTP against the
# running sglang server) on a compute node so it persists independently of the
# Lab shell. Outputs MUST be written under $SILICO_EXPERIMENT_ARTIFACTS_DIR
# (the compute node's worktree copy is not durable).
#
# Usage: sbatch --job-name=slco-... src/run_driver.sh <python-args...>
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=06:00:00
set -euo pipefail

cd "$SILICO_EXPERIMENT_DIR"
echo "DRIVER_START $(date -u +%H:%M:%S) args: $*"
uv run python "$@"
echo "DRIVER_DONE $(date -u +%H:%M:%S)"

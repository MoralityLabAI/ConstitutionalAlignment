#!/bin/bash
#SBATCH --partition=a100
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=06:00:00
set -euo pipefail
cd ~/.silico/libraries/goodfire-core
uv run hf download PrimeIntellect/INTELLECT-3 \
  --local-dir "$SILICO_EXPERIMENT_ARTIFACTS_DIR/models/INTELLECT-3" \
  --max-workers 16
echo DOWNLOAD_DONE

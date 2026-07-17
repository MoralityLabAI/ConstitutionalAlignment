#!/bin/bash
#SBATCH --partition=a100
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:20:00
set -euo pipefail
cd ~/.silico/libraries/goodfire-core
uv run python "$SILICO_EXPERIMENT_DIR/src/prep_data.py"

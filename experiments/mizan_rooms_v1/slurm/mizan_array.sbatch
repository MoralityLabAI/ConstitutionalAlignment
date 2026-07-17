#!/usr/bin/env bash
#SBATCH --job-name=mizan-v1
#SBATCH --array=0-14%3
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=artifacts/mizan_rooms_v1/slurm/%A_%a.out
#SBATCH --error=artifacts/mizan_rooms_v1/slurm/%A_%a.err

set -euo pipefail

: "${MIZAN_MODEL:?Set MIZAN_MODEL to the exact served model revision}"
: "${MIZAN_ANALYSIS_PLAN_SHA256:?Set the frozen pre-analysis SHA-256}"

REPO_DIR="${REPO_DIR:-$PWD}"
cd "$REPO_DIR"
mkdir -p artifacts/mizan_rooms_v1/slurm

conditions=(neutral constitutional secular_omniscient eschatological unreliable_authority)
seeds=(11 23 47)
condition_index=$((SLURM_ARRAY_TASK_ID % 5))
seed_index=$((SLURM_ARRAY_TASK_ID / 5))
condition="${conditions[$condition_index]}"
seed="${seeds[$seed_index]}"
policy="${MIZAN_POLICY:-openai-compatible}"
output_root="${MIZAN_OUTPUT_ROOT:-${TESSERACT_ARTIFACT_DIR:-artifacts/mizan_rooms_v1/evaluation}}"
output_dir="${output_root}/${MIZAN_MODEL//\//_}/${condition}_s${seed}"

common_args=(
  --condition "$condition"
  --split evaluation
  --seed "$seed"
  --replicates 3
  --blinding-seed 20260716
  --model-id "$MIZAN_MODEL"
  --policy "$policy"
  --temperature "${MIZAN_TEMPERATURE:-0.2}"
  --top-p "${MIZAN_TOP_P:-1.0}"
  --max-tokens "${MIZAN_MAX_TOKENS:-180}"
  --timeout-seconds "${MIZAN_TIMEOUT_SECONDS:-180}"
  --output-dir "$output_dir"
  --unseal-evaluation
  --analysis-plan-sha256 "$MIZAN_ANALYSIS_PLAN_SHA256"
)

if [[ "$policy" == "openai-compatible" ]]; then
  : "${MIZAN_API_BASE:?Set MIZAN_API_BASE for openai-compatible policy}"
  python scripts/run_mizan_rooms.py "${common_args[@]}" --api-base "$MIZAN_API_BASE"
elif [[ "$policy" == "command" ]]; then
  : "${MIZAN_AGENT_COMMAND:?Set MIZAN_AGENT_COMMAND for command policy}"
  python scripts/run_mizan_rooms.py "${common_args[@]}" --agent-command "$MIZAN_AGENT_COMMAND"
else
  echo "MIZAN_POLICY must be openai-compatible or command for cluster runs" >&2
  exit 2
fi

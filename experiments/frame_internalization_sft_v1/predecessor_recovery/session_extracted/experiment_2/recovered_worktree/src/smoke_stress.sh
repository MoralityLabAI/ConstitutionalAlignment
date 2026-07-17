#!/bin/bash
# Smoke: 10 prompts, F0 free-tier, one sample, for each stressor. Verifies
# multi-turn assembly, native-think scratchpad survival at long context, and
# tag parsing. Writes to $SILICO_EXPERIMENT_ARTIFACTS_DIR/generations/smoke/.
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=01:00:00
set -euo pipefail
cd "$SILICO_EXPERIMENT_DIR"

URL=$(sed 's/URL=//' results/server_url.txt)
POOLDIR="$SILICO_EXPERIMENT_ARTIFACTS_DIR/materials/practice_pools"
OUT="$SILICO_EXPERIMENT_ARTIFACTS_DIR/generations/smoke"
mkdir -p "$OUT"
CFG=data/gen_config.json
Q=data/harmful_150.jsonl

echo "SMOKE_START $(date -u +%H:%M:%S)"
for spec in "S1 10" "S2 generic" "S3 practice"; do
  set -- $spec
  st=$1; var=$2
  echo "=== smoke $st/$var ==="
  uv run python src/gen_stress.py --url "$URL" --stressor "$st" --variant "$var" \
    --frames F0 --tiers free --queries "$Q" --samples 1 --limit 10 \
    --gen-config "$CFG" --concurrency 10 --max-tokens 6000 --pool-dir "$POOLDIR" \
    --out "$OUT/smoke_${st}_${var}.jsonl"
done
echo "SMOKE_DONE $(date -u +%H:%M:%S)"
